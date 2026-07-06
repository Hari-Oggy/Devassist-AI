import subprocess
import json
import shlex
from typing import Optional, Any, Dict, List
from core.logger import get_logger

logger = get_logger("services.mcp_client")

class SyncStdioMCPClient:
    """Synchronous client for Model Context Protocol (MCP) servers using stdio transport."""

    def __init__(self, name: str, command: str, args: List[str]):
        self.name = name
        self.command = command
        self.args = args
        self.process: Optional[subprocess.Popen] = None
        self._next_id = 1

    def start(self) -> bool:
        """Spawn the child process and initialize the protocol session."""
        try:
            logger.info("Starting MCP server process '%s': %s %s", self.name, self.command, self.args)
            # Combine command and args into a single list
            full_cmd = [self.command] + self.args
            self.process = subprocess.Popen(
                full_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1  # Line buffered
            )
            
            # Protocol initialization sequence
            self.request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "DevAssist", "version": "1.0"}
            })
            self.notify("notifications/initialized")
            logger.info("Successfully initialized MCP server '%s'", self.name)
            return True
        except Exception as e:
            logger.error("Failed to start MCP server '%s': %s", self.name, e)
            self.stop()
            return False

    def stop(self):
        """Clean up process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

    def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Send a JSON-RPC request and wait synchronously for the response line."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError(f"MCP server '{self.name}' process not running")

        req_id = self._next_id
        self._next_id += 1
        
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        }
        
        message = json.dumps(req)
        self.process.stdin.write(message + "\n")
        self.process.stdin.flush()
        
        # Block until the response line arrives
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"MCP server '{self.name}' closed stdout stream")
            
        try:
            response = json.loads(line)
        except Exception as e:
            raise RuntimeError(f"Failed to parse JSON-RPC response from '{self.name}': {e}. Raw line: {line}")
            
        # Match response ID
        if response.get("id") != req_id:
            logger.warning("MCP client '%s' received mismatched message ID: expected %d, got %s", 
                           self.name, req_id, response.get("id"))
            
        if "error" in response:
            raise RuntimeError(response["error"].get("message", "Unknown error"))
            
        return response.get("result")

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Send a JSON-RPC notification (no ID, no response expected)."""
        if not self.process or not self.process.stdin:
            raise RuntimeError(f"MCP server '{self.name}' process not running")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        message = json.dumps(notification)
        self.process.stdin.write(message + "\n")
        self.process.stdin.flush()

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all tools registered by this server."""
        try:
            res = self.request("tools/list")
            return res.get("tools", [])
        except Exception as e:
            logger.error("Failed to list tools for MCP server '%s': %s", self.name, e)
            return []

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool registered by this server."""
        try:
            return self.request("tools/call", {
                "name": name,
                "arguments": arguments
            })
        except Exception as e:
            logger.error("Failed to call tool '%s' on MCP server '%s': %s", name, self.name, e)
            return {"isError": True, "content": [{"type": "text", "text": f"Error: {e}"}]}


class SyncMCPClientManager:
    """Synchronous manager to coordinate and query multiple active MCP servers."""

    def __init__(self):
        self.clients: Dict[str, SyncStdioMCPClient] = {}

    def init_active_servers(self, session_sync_helper):
        """Find and start all active servers declared in the database.
        
        Expects a synchronous database execution or queries from a synchronous session.
        """
        # We can also dynamically load them from a config or environment since Celery / worker
        # might run outside the FastAPI thread.
        # To avoid complex async-to-sync DB wrappers, we can also load from a standard config file
        # or load directly. Let's do a simple DB query.
        from models.entities import MCPServer
        from sqlalchemy import select
        
        # If we are inside Celery, we run DB queries synchronously or via a sync engine helper
        # Since we are using SQLAlchemy async, we query the DB before starting the worker,
        # or we run a small sync connection here.
        # Alternatively, we can let the worker fetch the list using a helper.
        pass

    def load_from_config(self, servers_list: List[Dict[str, Any]]):
        """Helper to initialize client sessions from a list of dicts."""
        for s in servers_list:
            name = s.get("name")
            command = s.get("command")
            args_raw = s.get("args")
            
            if name and command:
                args_list = []
                if args_raw:
                    try:
                        args_list = json.loads(args_raw)
                        if not isinstance(args_list, list):
                            args_list = shlex.split(args_raw)
                    except Exception:
                        args_list = shlex.split(args_raw)
                
                client = SyncStdioMCPClient(name, command, args_list)
                if client.start():
                    self.clients[name] = client

    def shutdown(self):
        """Terminate all active connection sessions."""
        for client in self.clients.values():
            client.stop()
        self.clients.clear()

    def get_combined_tools(self) -> List[Dict[str, Any]]:
        """Fetch tools across all active servers, prefixing names with server tags."""
        combined = []
        for name, client in self.clients.items():
            tools = client.list_tools()
            for t in tools:
                combined.append({
                    "name": f"{name}__{t['name']}",
                    "description": t.get("description", ""),
                    "input_schema": t.get("inputSchema", {})
                })
        return combined

    def call_tool(self, namespaced_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Route tool invocation to the correct server based on namespace prefix."""
        if "__" not in namespaced_name:
            raise ValueError(f"Invalid namespaced tool name: {namespaced_name}")
        
        server_name, tool_name = namespaced_name.split("__", 1)
        client = self.clients.get(server_name)
        if not client:
            raise ValueError(f"MCP server '{server_name}' is not running")
        
        return client.call_tool(tool_name, arguments)

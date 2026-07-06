"use client";

import { useEffect, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Info, Plus, Trash2, Shield, Settings, Server, Terminal, CheckCircle2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader, GlassCard, LoadingSpinner } from "@/components/ui/shared";
import { useDashboardStore } from "@/lib/stores/dashboardStore";

const SUGGESTED_INTEGRATIONS = [
  { name: 'Notion', domain: 'mcp.notion.com', icon: 'N', command: 'npx', args: '-y @modelcontextprotocol/server-notion' },
  { name: 'Linear', domain: 'mcp.linear.app', icon: 'L', command: 'npx', args: '-y @modelcontextprotocol/server-linear' },
  { name: 'GitHub', domain: 'mcp.github.com', icon: 'G', command: 'npx', args: '-y @modelcontextprotocol/server-github' },
  { name: 'Sentry', domain: 'mcp.sentry.dev', icon: 'S', command: 'npx', args: '-y @modelcontextprotocol/server-sentry' },
];

export default function Integrations() {
  const { mcpServers, loadingMcp, fetchMcpServers, addMcpServer, removeMcpServer } = useDashboardStore();
  const [showAddForm, setShowAddForm] = useState(false);
  const [name, setName] = useState("");
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMcpServers();
  }, [fetchMcpServers]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !command) {
      setError("Name and command are required.");
      return;
    }
    setAdding(true);
    setError(null);
    try {
      await addMcpServer({
        name,
        transport_type: "stdio",
        command,
        args: args ? JSON.stringify(args.split(" ")) : "[]"
      });
      setName("");
      setCommand("");
      setArgs("");
      setShowAddForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAdding(false);
    }
  };

  const handleAddSuggested = async (suggested: typeof SUGGESTED_INTEGRATIONS[0]) => {
    setError(null);
    try {
      await addMcpServer({
        name: suggested.name.toLowerCase(),
        transport_type: "stdio",
        command: suggested.command,
        args: JSON.stringify(suggested.args.split(" "))
      });
      alert(`Successfully registered ${suggested.name} MCP server!`);
    } catch (err) {
      alert("Failed to add suggested integration: " + (err instanceof Error ? err.message : String(err)));
    }
  };

  const handleDelete = async (id: number) => {
    if (confirm("Are you sure you want to remove this MCP server connection?")) {
      try {
        await removeMcpServer(id);
      } catch (err) {
        alert("Failed to remove server: " + (err instanceof Error ? err.message : String(err)));
      }
    }
  };

  return (
    <div className="mx-auto max-w-[1280px] p-8 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <PageHeader
        title="Integrations"
        subtitle="Configure Model Context Protocol (MCP) servers and third-party developer tool connectors."
        action={
          <Button 
            onClick={() => setShowAddForm(!showAddForm)}
            className="bg-violet-600 hover:bg-violet-500 text-white rounded-xl h-10 px-4 text-[13px] font-bold gap-2 transition-all duration-200"
          >
            <Plus className="h-4 w-4" />
            {showAddForm ? "Close Form" : "New MCP Server"}
          </Button>
        }
      />

      {showAddForm && (
        <GlassCard className="animate-in slide-in-from-top-4 duration-300">
          <h3 className="text-[16px] font-bold text-white mb-4 flex items-center gap-2">
            <Server className="h-5 w-5 text-violet-400" />
            Add Custom MCP Server
          </h3>
          <form onSubmit={handleSubmit} className="space-y-4 max-w-xl">
            <div>
              <label className="block text-[12px] font-bold text-white/50 mb-1.5 uppercase">Server Name</label>
              <input
                type="text"
                placeholder="e.g., local-db"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-2.5 text-[14px] bg-white/[0.03] border border-white/[0.07] rounded-xl text-white focus:outline-none focus:border-violet-500/50 transition-colors"
                required
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-[12px] font-bold text-white/50 mb-1.5 uppercase">Executable Command</label>
                <input
                  type="text"
                  placeholder="e.g., node, python, npx"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  className="w-full px-4 py-2.5 text-[14px] bg-white/[0.03] border border-white/[0.07] rounded-xl text-white focus:outline-none focus:border-violet-500/50 transition-colors"
                  required
                />
              </div>
              <div>
                <label className="block text-[12px] font-bold text-white/50 mb-1.5 uppercase">Arguments (Space separated)</label>
                <input
                  type="text"
                  placeholder="e.g., path/to/server.js arg1 arg2"
                  value={args}
                  onChange={(e) => setArgs(e.target.value)}
                  className="w-full px-4 py-2.5 text-[14px] bg-white/[0.03] border border-white/[0.07] rounded-xl text-white focus:outline-none focus:border-violet-500/50 transition-colors"
                />
              </div>
            </div>
            
            {error && (
              <div className="flex gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/25 text-rose-400 text-[13px] items-center">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Button 
                type="button" 
                variant="outline" 
                onClick={() => setShowAddForm(false)}
                className="bg-transparent border-white/10 text-white/70 hover:bg-white/[0.04]"
              >
                Cancel
              </Button>
              <Button 
                type="submit" 
                disabled={adding}
                className="bg-violet-600 hover:bg-violet-500 text-white font-bold"
              >
                {adding ? "Connecting..." : "Add Server"}
              </Button>
            </div>
          </form>
        </GlassCard>
      )}

      <Tabs defaultValue="mcp" className="w-full">
        <TabsList className="bg-white/[0.03] border border-white/[0.07] p-1 mb-6 rounded-xl">
          <TabsTrigger value="mcp" className="data-[state=active]:bg-white/[0.06] data-[state=active]:text-white text-white/40 rounded-lg text-[13px] font-semibold px-4 py-2">
            Active MCP Servers
          </TabsTrigger>
          <TabsTrigger value="suggested" className="data-[state=active]:bg-white/[0.06] data-[state=active]:text-white text-white/40 rounded-lg text-[13px] font-semibold px-4 py-2">
            Suggested Integrations
          </TabsTrigger>
        </TabsList>
        
        <TabsContent value="mcp" className="space-y-6">
          <GlassCard className="flex gap-4 items-start">
            <Info className="h-5 w-5 text-violet-400 shrink-0 mt-0.5" />
            <p className="text-[13px] text-white/50 leading-relaxed">
              Model Context Protocol (MCP) server connections let DevAssist's review pipeline query external context (e.g., search documents, read issues) during code analysis. Standard output/input transport is configured locally.
            </p>
          </GlassCard>

          {loadingMcp ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : mcpServers.length === 0 ? (
            <GlassCard className="text-center py-16 flex flex-col items-center justify-center">
              <div className="h-16 w-16 bg-white/[0.03] border border-white/[0.06] rounded-2xl flex items-center justify-center mb-4">
                <Server className="h-8 w-8 text-white/30" />
              </div>
              <h4 className="text-[16px] font-bold text-white mb-1.5">No MCP servers registered</h4>
              <p className="text-white/40 max-w-sm text-[13px] leading-relaxed mb-6">
                Connect your first MCP server (like Notion or GitHub context server) to give DevAssist AI more codebase insights.
              </p>
              <Button 
                onClick={() => setShowAddForm(true)}
                className="bg-violet-600/10 border border-violet-500/20 text-violet-400 hover:bg-violet-600/20 rounded-xl"
              >
                Register a Server
              </Button>
            </GlassCard>
          ) : (
            <div className="grid gap-4">
              {mcpServers.map((server) => (
                <GlassCard key={server.id} noPad className="hover:border-white/[0.12] transition-all duration-300">
                  <div className="p-5 flex items-center justify-between gap-6">
                    <div className="flex items-center gap-4 min-w-0">
                      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-500/10 border border-violet-500/20 text-violet-400 shrink-0">
                        <Terminal className="h-5 w-5" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h3 className="text-[14px] font-bold text-white truncate">{server.name}</h3>
                          <span className="text-[9px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full uppercase tracking-wider">
                            Active
                          </span>
                        </div>
                        <p className="text-[12px] text-white/45 mt-1 font-mono truncate">
                          {server.command} {server.args ? JSON.parse(server.args).join(" ") : ""}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(server.id)}
                      className="p-2.5 rounded-xl border border-rose-500/20 bg-rose-500/5 text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/30 transition-all duration-200"
                      title="Remove Connection"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="suggested" className="grid gap-4">
          {SUGGESTED_INTEGRATIONS.map((integration) => {
            const isInstalled = mcpServers.some(s => s.name === integration.name.toLowerCase());
            return (
              <GlassCard key={integration.name} noPad className="hover:border-white/[0.12] transition-all duration-300">
                <div className="p-5 flex items-center justify-between gap-6">
                  <div className="flex items-center gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/[0.04] border border-white/[0.07] text-white font-bold text-[18px]">
                      {integration.icon}
                    </div>
                    <div>
                      <h3 className="text-[14px] font-bold text-white">{integration.name}</h3>
                      <p className="text-[12px] text-white/40 mt-1">{integration.domain}</p>
                    </div>
                  </div>
                  {isInstalled ? (
                    <span className="flex items-center gap-1.5 text-[12px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-xl">
                      <CheckCircle2 className="h-4 w-4" />
                      Connected
                    </span>
                  ) : (
                    <Button 
                      onClick={() => handleAddSuggested(integration)}
                      className="bg-violet-600/10 border border-violet-500/20 text-violet-400 hover:bg-violet-600/20 rounded-xl text-[12px] font-bold"
                    >
                      <Plus className="mr-1.5 h-3.5 w-3.5" />
                      Quick Add
                    </Button>
                  )}
                </div>
              </GlassCard>
            );
          })}
        </TabsContent>
      </Tabs>
    </div>
  );
}

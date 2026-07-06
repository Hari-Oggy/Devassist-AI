from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from models.database import get_db_session
from models.repositories import MCPServerRepo
from pydantic import BaseModel

router = APIRouter(prefix="/integrations", tags=["Integrations"])

class MCPServerCreate(BaseModel):
    name: str
    transport_type: str = "stdio"
    command: Optional[str] = None
    args: Optional[str] = None
    url: Optional[str] = None

class MCPServerResponse(BaseModel):
    id: int
    name: str
    transport_type: str
    command: Optional[str]
    args: Optional[str]
    url: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True

@router.get("", response_model=List[MCPServerResponse])
async def list_mcp_servers(session: AsyncSession = Depends(get_db_session)):
    """List all configured MCP servers."""
    servers = await MCPServerRepo.get_all_active(session)
    return servers

@router.post("", response_model=MCPServerResponse)
async def create_mcp_server(
    server_in: MCPServerCreate,
    session: AsyncSession = Depends(get_db_session)
):
    """Register a new MCP server."""
    existing = await MCPServerRepo.get_by_name(session, server_in.name)
    if existing:
        raise HTTPException(status_code=400, detail=f"MCP Server '{server_in.name}' already registered.")
        
    db_server = await MCPServerRepo.create(
        session=session,
        name=server_in.name,
        transport_type=server_in.transport_type,
        command=server_in.command,
        args=server_in.args,
        url=server_in.url
    )
    return db_server

@router.delete("/{server_id}")
async def delete_mcp_server(
    server_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """Delete an MCP server registration."""
    server = await MCPServerRepo.get_by_id(session, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")
        
    await session.delete(server)
    await session.commit()
    return {"message": f"MCP Server {server_id} successfully deleted"}

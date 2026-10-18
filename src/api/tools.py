"""Local MCP management; discovery never invokes a business tool."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.providers import local_management
from tools import managed
from tools.registry import ToolRegistry
from tools.settings import MCPSettings
from utils.execution import public_data

router = APIRouter(prefix="/settings/mcp", dependencies=[Depends(local_management)])


def refresh_tools():
    from api.workbench import systems
    specs = managed.configured_tools()
    for system in systems.values():
        system.retriever.registry.replace_external(specs)


def server_or_404(identity):
    try:
        return managed.get_store().get(identity)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("")
async def list_servers():
    return public_data({"items": managed.get_store().list()})


@router.post("")
async def add_server(body: MCPSettings):
    try:
        return {"id": managed.get_store().save(body)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/{identity}")
async def update_server(identity: str, body: MCPSettings):
    server_or_404(identity)
    managed.get_store().save(body, identity)
    refresh_tools()
    return {"id": identity}


@router.delete("/{identity}")
async def delete_server(identity: str):
    managed.get_store().remove(identity)
    refresh_tools()
    return {"removed": True}


class Activation(BaseModel):
    enabled: bool
    selected_tools: list[str] = Field(default_factory=list, max_length=16)


@router.patch("/{identity}")
async def activate_server(identity: str, body: Activation):
    server_or_404(identity)
    try:
        managed.get_store().activate(identity, body.enabled, body.selected_tools)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    refresh_tools()
    return {"updated": True}


async def while_connected(request: Request, operation):
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=0.2)
            if done:
                break
            if await request.is_disconnected():
                raise HTTPException(499, "请求已取消")
        return await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@router.post("/{identity}/discover")
async def discover_tools(identity: str, request: Request):
    server_or_404(identity)
    try:
        return await while_connected(request, managed.discover(identity))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    finally:
        refresh_tools()


class ToolTrial(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.post("/{identity}/call")
async def try_tool(identity: str, body: ToolTrial, request: Request):
    server = server_or_404(identity)
    tool = next((tool for tool in server["tools"] if tool["name"] == body.name), None)
    if not tool or not server["check_ok"]:
        raise HTTPException(409, "请先连接服务并发现工具")
    if not tool["read_only"]:
        raise HTTPException(422, "工作台仅支持声明只读的查询工具")
    if len(json.dumps(body.arguments)) > 20000:
        raise HTTPException(422, "试运行参数过大")
    registry = ToolRegistry()
    spec = managed.make_spec(server, tool, manual=True)
    registry.register(spec)
    return public_data(await while_connected(request, registry.invoke(spec.name, body.arguments)))

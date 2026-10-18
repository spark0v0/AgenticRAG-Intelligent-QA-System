"""Discovery-to-registry adapter for user-configured MCP query tools."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.base import ToolDocument, ToolResult, ToolSpec
from tools.mcp_client import MCPConnection, MCPClientError
from tools.settings import ToolSettingsStore
from utils.execution import public_data

_store: ToolSettingsStore | None = None


def get_store():
    global _store
    if _store is None:
        _store = ToolSettingsStore(Path(os.getenv("AGENTICRAG_TOOLS", "data/settings/tools.sqlite3")))
    return _store


def tool_id(server_id: str, name: str):
    return f"mcp_{server_id}_{hashlib.sha256(name.encode()).hexdigest()[:12]}"


def validate_schema(schema):
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("工具必须提供 object 类型参数 Schema")
    if len(json.dumps(schema)) > 32_000:
        raise ValueError("工具参数 Schema 过大")
    # Validation must never fetch arbitrary external resources.
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"$ref", "$dynamicRef"} and (not isinstance(item, str) or not item.startswith("#")):
                    raise ValueError("工具 Schema 仅允许本地引用")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(schema)
    Draft202012Validator.check_schema(schema)


def connection_error(exc):
    if isinstance(exc, TimeoutError):
        return "MCP 请求超时，请检查服务后重试"
    if isinstance(exc, MCPClientError):
        return str(exc)
    return "MCP 连接或协议处理失败，请检查服务地址、启动程序、凭据及协议支持"


async def discover(identity):
    store = get_store()
    server = store.get(identity)
    tools = []
    try:
        remote = await MCPConnection(server).list_tools()
        names = set()
        for item in remote:
            name = item.get("name")
            if not isinstance(name, str) or not name or len(name) > 200 or name in names:
                raise MCPClientError("服务返回重复或无效工具名称")
            names.add(name)
            schema = item.get("inputSchema")
            validate_schema(schema)
            tools.append({"name": name, "description": str(item.get("description") or name)[:2000],
                          "schema": schema, "read_only": (item.get("annotations") or {}).get("readOnlyHint") is True})
        ok, message = True, f"连接成功，发现 {len(tools)} 个工具；请选择需要用于问答的只读工具"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        ok, message, tools = False, connection_error(exc), []
    if not store.record_check(identity, server["revision"], tools, ok, message):
        raise ValueError("检测期间配置已变化，请重新连接")
    return {"ok": ok, "message": message}


def normalize_result(response, server, tool):
    if response.get("isError"):
        return ToolResult(status="error", error="MCP 工具返回执行错误，请检查参数或服务端状态")
    text = "\n\n".join(str(block.get("text", "")) for block in response.get("content", [])
                       if block.get("type") == "text")
    if not text and response.get("structuredContent") is not None:
        text = json.dumps(response["structuredContent"], ensure_ascii=False)
    documents = [ToolDocument(content=public_data(text[:20000]),
        source=f"mcp://{server['id']}/{tool_id(server['id'], tool['name'])}", score=0.6,
        metadata={"server_id": server["id"], "server_name": server["name"], "tool": tool["name"],
                  "source_type": "mcp", "title": f"{server['name']} · {tool['name']}", "truncated": len(text) > 20000})] if text else []
    return ToolResult(documents=documents, metadata={"backend": "mcp", "server_name": server["name"],
                                                   "empty_result": not documents})


def make_spec(server, tool, *, manual=False):
    async def invoke(payload):
        store = get_store()
        current = store.get(server["id"])
        if current["revision"] != server["revision"] or (not manual and not current["enabled"]):
            return ToolResult(status="error", error="工具配置已变化或停用，请重新发起请求")
        started = time.perf_counter()
        try:
            response = await MCPConnection(server).call_tool(tool["name"], payload.payload)
            result = normalize_result(response, server, tool)
        except asyncio.CancelledError:
            store.record_call(server["id"], server["revision"], {"tool": tool["name"], "status": "cancelled", "at": time.time()})
            raise
        except Exception as exc:
            result = ToolResult(status="timeout" if isinstance(exc, TimeoutError) else "error", error=connection_error(exc))
        store.record_call(server["id"], server["revision"], {"tool": tool["name"], "status": result.status,
                          "at": time.time(), "duration_ms": round((time.perf_counter() - started) * 1000)})
        return result
    return ToolSpec(name=tool_id(server["id"], tool["name"]), description=f"{server['name']}: {tool['description']}",
                    handler=invoke, json_schema=tool["schema"], protocol="mcp", tags=["mcp", "external"],
                    timeout_seconds=server["timeout_seconds"] + 3,
                    metadata={"server_id": server["id"], "display_name": f"{server['name']} / {tool['name']}"})


def configured_tools():
    return [make_spec(server, tool) for server in get_store().list() if server["enabled"] and server["check_ok"]
            for tool in server["tools"] if tool["name"] in server["selected_tools"] and tool["read_only"]]

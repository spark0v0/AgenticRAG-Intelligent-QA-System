"""Bounded SDK sessions; every operation owns and closes its transport."""
from __future__ import annotations
import os
from contextlib import asynccontextmanager
import anyio
import httpx2
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from utils.execution import register_secret


class MCPClientError(RuntimeError):
    pass


class MCPConnection:
    def __init__(self, settings: dict):
        self.settings = settings

    @asynccontextmanager
    async def connect(self):
        cfg = self.settings
        with anyio.fail_after(cfg.get('timeout_seconds', 15)):
            if cfg['transport'] == 'stdio':
                env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
                for name in cfg.get('env_names', []):
                    if name not in os.environ:
                        raise MCPClientError('所需后端环境变量未配置')
                    env[name] = os.environ[name]
                    register_secret(env[name])
                params = StdioServerParameters(command=cfg['command'], args=cfg.get('args', []), cwd=cfg.get('cwd'), env=env)
                # Server stderr may contain credentials. Never forward it to app logs.
                with open(os.devnull, 'w') as errlog:
                    async with Client(stdio_client(params, errlog=errlog), cache=None) as client:
                        yield client
            else:
                headers = {}
                if name := cfg.get('token_env'):
                    token = os.environ.get(name)
                    if not token:
                        raise MCPClientError('所需后端环境变量未配置')
                    register_secret(token)
                    headers['Authorization'] = f'Bearer {token}'
                async with httpx2.AsyncClient(headers=headers, timeout=cfg.get('timeout_seconds', 15), follow_redirects=False) as http:
                    async with Client(streamable_http_client(cfg['url'], http_client=http), cache=None) as client:
                        yield client

    async def list_tools(self):
        async with self.connect() as client:
            tools, cursor, seen = [], None, set()
            for _ in range(10):
                page = await client.list_tools(cursor=cursor)
                tools.extend(tool.model_dump(by_alias=True, exclude_none=True) for tool in page.tools)
                if len(tools) > 80:
                    raise MCPClientError('服务工具超过 80 个，请拆分服务范围')
                cursor = page.next_cursor
                if not cursor:
                    return tools
                if cursor in seen:
                    break
                seen.add(cursor)
            raise MCPClientError('工具列表分页异常')

    async def call_tool(self, name, arguments):
        async with self.connect() as client:
            result = await client.call_tool(name, arguments)
            return result.model_dump(by_alias=True, exclude_none=True)


class StdioMCPClient(MCPConnection):
    def __init__(self, command: list[str], cwd: str | None = None):
        super().__init__({'transport': 'stdio', 'command': command[0], 'args': command[1:], 'cwd': cwd})

    async def close(self):
        pass  # Sessions belong to each operation, not to the adapter lifetime.

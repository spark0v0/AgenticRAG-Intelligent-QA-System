"""Offline MCP fixture: only fixed public test data; supports stdio and HTTP."""
import asyncio
import sys
from pathlib import Path

from mcp.server import MCPServer
from mcp_types import ToolAnnotations

server = MCPServer("workbench-test-tools")


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def city_info(city: str, days: int = 1) -> str:
    """Return fixed city information for a transport test, not a real weather service."""
    return f"测试城市：{city}；天数：{days}"


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
async def slow_query(marker: str) -> str:
    """Cancellation fixture: writes only the caller's temporary marker."""
    try:
        Path(marker).write_text("started", encoding="utf8")
        await asyncio.sleep(60)
    finally:
        Path(marker).write_text("closed", encoding="utf8")
    return "done"


@server.tool()
def unspecified_action() -> str:
    """No read-only declaration: must not be eligible for automatic calling."""
    return "not selectable"


if __name__ == '__main__':
    if len(sys.argv) > 1:
        server.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[1]))
    else:
        server.run()

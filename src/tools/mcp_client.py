from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any, Dict, List


class MCPClientError(RuntimeError):
    pass


class StdioMCPClient:
    def __init__(self, command: List[str], cwd: str | None = None):
        self.command = command
        self.cwd = cwd
        self._request_id = 0

    async def start(self) -> None:
        return None

    async def list_tools(self) -> List[Dict[str, Any]]:
        response = await asyncio.to_thread(self._run_request, "tools/list", {})
        return response.get("tools", [])

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._run_request, "tools/call", {"name": name, "arguments": arguments})

    async def close(self) -> None:
        return None

    def _run_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        with subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.cwd,
        ) as process:
            self._sync_request(
                process,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "agenticrag-local-client", "version": "1.0.0"},
                },
            )
            self._sync_notify(process, "notifications/initialized", {})
            result = self._sync_request(process, method, params)
            process.terminate()
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.kill()
            return result

    def _sync_request(self, process: subprocess.Popen[bytes], method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        self._write_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            },
        )
        while True:
            message = self._read_message(process)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise MCPClientError(str(message["error"]))
            return message.get("result", {})

    def _sync_notify(self, process: subprocess.Popen[bytes], method: str, params: Dict[str, Any]) -> None:
        self._write_message(
            process,
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            },
        )

    def _write_message(self, process: subprocess.Popen[bytes], payload: Dict[str, Any]) -> None:
        if process.stdin is None:
            raise MCPClientError("MCP process stdin is not available.")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        process.stdin.write(header + body)
        process.stdin.flush()

    def _read_message(self, process: subprocess.Popen[bytes]) -> Dict[str, Any]:
        if process.stdout is None:
            raise MCPClientError("MCP process stdout is not available.")

        headers: Dict[str, str] = {}
        while True:
            line = process.stdout.readline()
            if not line:
                stderr = self._read_stderr(process)
                raise MCPClientError(f"MCP process closed unexpectedly. {stderr}".strip())
            stripped = line.decode("utf-8").strip()
            if not stripped:
                break
            name, _, value = stripped.partition(":")
            headers[name.lower()] = value.strip()

        length = int(headers.get("content-length", "0"))
        body = process.stdout.read(length)
        return json.loads(body.decode("utf-8"))

    def _read_stderr(self, process: subprocess.Popen[bytes]) -> str:
        if process.stderr is None:
            return ""
        try:
            return process.stderr.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

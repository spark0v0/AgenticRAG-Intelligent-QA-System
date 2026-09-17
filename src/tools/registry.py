from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, Iterable

from pydantic import BaseModel, ValidationError
from utils.execution import current_execution

from .base import ToolResult, ToolSpec


class ToolRegistry:
    def __init__(self, default_timeout_seconds: float = 15.0) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        self.default_timeout_seconds = default_timeout_seconds

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_tools(self) -> Iterable[ToolSpec]:
        return self._tools.values()

    def export_function_schemas(self) -> list[Dict[str, Any]]:
        return [tool.as_function_schema() for tool in self.list_tools()]

    async def invoke(self, name: str, payload: Dict[str, object]) -> Dict[str, object]:
        tool = self.get(name)
        if not tool:
            raise KeyError(f"Unknown tool: {name}")

        started = time.perf_counter()
        execution = current_execution.get()
        call = {"call_id": str(uuid.uuid4()), "tool": name, "protocol": tool.protocol,
                "input": payload, "started_at": time.time()}
        if execution:
            execution.emit("tool", {**call, "status": "running"})

        try:
            validated_payload = self._validate_input(tool, payload)
            raw_result = await asyncio.wait_for(
                tool.handler(validated_payload),
                timeout=tool.timeout_seconds or self.default_timeout_seconds,
            )
            result = self._normalize_result(raw_result)
        except asyncio.CancelledError:
            if execution:
                execution.emit("tool", {**call, "status": "cancelled", "finished_at": time.time(),
                                        "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
            raise
        except asyncio.TimeoutError:
            result = ToolResult(
                status="timeout",
                error=f"Tool '{name}' timed out after {tool.timeout_seconds or self.default_timeout_seconds:.1f}s.",
            )
        except ValidationError as exc:
            result = ToolResult(
                status="error",
                error=f"Tool '{name}' input validation failed: {exc.errors(include_url=False)}",
            )
        except Exception as exc:
            result = ToolResult(status="error", error=str(exc))

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if execution:
            execution.emit("tool", {**call, "status": result.status, "finished_at": time.time(),
                                    "duration_ms": duration_ms, "document_count": len(result.documents),
                                    "error": result.error, "output": [doc.content[:180] for doc in result.documents[:3]]})
        merged_metadata = {
            **result.metadata,
            "tool_name": name,
            "protocol": tool.protocol,
            "tags": tool.tags,
            "latency_ms": duration_ms,
        }
        return {
            "documents": [item.model_dump() for item in result.documents],
            "metadata": merged_metadata,
            "status": result.status,
            "error": result.error,
        }

    def _validate_input(self, tool: ToolSpec, payload: Dict[str, object]) -> BaseModel:
        if tool.input_model is None:
            return _PayloadWrapper(payload=payload)
        return tool.input_model.model_validate(payload)

    def _normalize_result(self, raw_result: ToolResult | Dict[str, Any]) -> ToolResult:
        if isinstance(raw_result, ToolResult):
            return raw_result
        if isinstance(raw_result, dict):
            return ToolResult.model_validate(raw_result)
        raise TypeError(f"Unsupported tool result type: {type(raw_result)!r}")


class _PayloadWrapper(BaseModel):
    payload: Dict[str, object]

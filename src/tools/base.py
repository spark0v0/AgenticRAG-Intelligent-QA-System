from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Literal, Type

from pydantic import BaseModel, Field


ToolProtocol = Literal["native", "mcp", "function_calling"]


class ToolDocument(BaseModel):
    content: str
    source: str
    score: float = 0.0
    similarity: float | None = None
    confidence: float | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    documents: list[ToolDocument] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "error", "timeout"] = "success"
    error: str | None = None


ToolHandler = Callable[[BaseModel], Awaitable[ToolResult | Dict[str, Any]]]


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    input_model: Type[BaseModel] | None = None
    tags: list[str] = field(default_factory=list)
    timeout_seconds: float = 15.0
    protocol: ToolProtocol = "native"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def input_schema(self) -> Dict[str, Any]:
        if self.input_model is None:
            return {"type": "object", "properties": {}}
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return schema

    def as_function_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

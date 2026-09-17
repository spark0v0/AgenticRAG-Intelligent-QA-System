"""Per-request execution context and credential-safe public metadata."""
from __future__ import annotations
import os
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable

_local_secrets: set[str] = set()


def register_secret(value: str) -> None:
    if value:
        _local_secrets.add(value)


def public_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): public_data(v) for k, v in value.items() if str(k).lower() not in
                {"api_key", "authorization", "token", "password", "model_config", "raw_response"}}
    if isinstance(value, (list, tuple)):
        return [public_data(v) for v in value]
    if isinstance(value, str):
        if value.startswith("data:image/"):
            return value
        for secret in _local_secrets:
            value = value.replace(secret, "[redacted]")
        for key, secret in os.environ.items():
            if (key.endswith("API_KEY") or key.endswith("TOKEN")) and len(secret) > 8:
                value = value.replace(secret, "[redacted]")
        value = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[redacted]", value)
        return re.sub(r"(?i)(api_key|token|key|password)=([^&\s]+)", r"\1=[redacted]", value)
    return value


@dataclass
class Execution:
    session_id: str
    run_id: str
    streaming: bool
    record: Callable[[dict], None]
    listener: Callable[[dict], None] | None = None
    sequence: int = 0
    generation: int = 0
    draft: str = ""
    stages: dict[str, int] = field(default_factory=dict)

    def emit(self, kind: str, data: dict[str, Any]) -> dict:
        self.sequence += 1
        event = {"type": kind, "seq": self.sequence, "run_id": self.run_id,
                 "session_id": self.session_id, "timestamp": time.time(), "data": public_data(data)}
        if kind != "delta":
            self.record({**event, "data": {"status": "success"}} if kind == "completed" else event)
        if self.listener:
            self.listener(event)
        return event

    def begin_answer(self) -> None:
        self.generation += 1
        self.draft = ""
        self.emit("answer_start", {"generation": self.generation, "draft": True})

    def delta(self, text: str) -> None:
        self.draft += text
        self.emit("delta", {"text": text, "generation": self.generation})


current_execution: ContextVar[Execution | None] = ContextVar("execution", default=None)

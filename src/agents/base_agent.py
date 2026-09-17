from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from utils.execution import current_execution


class AgentInput(BaseModel):
    query: str
    context: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    session_id: Optional[str] = None


class AgentOutput(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class BaseAgent(ABC):
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Observe actual execution boundaries without changing agent algorithms."""
        execution = current_execution.get()
        if execution is None:
            return await self.process(input_data)
        name = self.name.lower()
        execution.stages[name] = execution.stages.get(name, 0) + 1
        stage = {"node": name, "stage_id": str(uuid.uuid4()), "round": execution.stages[name],
                 "input": input_data.query[:300], "started_at": time.time()}
        execution.emit("stage", {**stage, "status": "running"})
        if name == "generator":
            execution.begin_answer()
        started = time.perf_counter()
        try:
            output = await self.process(input_data)
        except BaseException as exc:
            status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "error"
            execution.emit("stage", {**stage, "status": status, "finished_at": time.time(),
                                     "output": "本阶段已取消" if status == "cancelled" else f"本阶段执行失败（{type(exc).__name__}）",
                                     "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
            raise
        execution.emit("stage", {**stage, "status": "success", "finished_at": time.time(),
                                 "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                                 "output": output.content[:400], "metadata": output.metadata})
        return output

    @abstractmethod
    async def process(self, input_data: AgentInput) -> AgentOutput:
        raise NotImplementedError

    def validate_input(self, input_data: AgentInput) -> bool:
        return bool(input_data.query and input_data.query.strip())

    def log_action(self, action: str, details: Dict[str, Any]) -> None:
        print(f"[{self.name}] {action}: {details}")

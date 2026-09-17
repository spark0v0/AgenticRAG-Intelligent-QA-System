from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from agents.base_agent import AgentInput, AgentOutput


def _serialize(output: AgentOutput) -> Dict[str, Any]:
    return {
        "content": output.content,
        "confidence": output.confidence,
        "metadata": output.metadata,
    }


@dataclass
class BaseDifyTool:
    name: str
    description: str
    system: Any

    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def _build_input(self, payload: Dict[str, Any], *, context: Dict[str, Any] | None = None) -> AgentInput:
        return AgentInput(
            query=str(payload.get("query", "")),
            context=context if context is not None else payload.get("context"),
            history=payload.get("history") or [],
            session_id=payload.get("session_id"),
        )


class RouterTool(BaseDifyTool):
    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        output = await self.system.router.process(self._build_input(payload))
        return _serialize(output)


class PlannerTool(BaseDifyTool):
    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        output = await self.system.planner.process(self._build_input(payload))
        return _serialize(output)


class RetrieverTool(BaseDifyTool):
    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        output = await self.system.retriever.process(self._build_input(payload))
        return _serialize(output)


class GeneratorTool(BaseDifyTool):
    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        context = {
            "documents": payload.get("documents") or [],
            "tasks": payload.get("tasks") or [],
            "critique": payload.get("critique") or {},
        }
        output = await self.system.generator.process(self._build_input(payload, context=context))
        return _serialize(output)


class CriticTool(BaseDifyTool):
    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        context = {
            "content": payload.get("answer", ""),
            "documents": payload.get("documents") or [],
        }
        output = await self.system.critic.process(self._build_input(payload, context=context))
        return _serialize(output)


class AgenticRAGQueryTool(BaseDifyTool):
    async def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.system.query(
            str(payload.get("query", "")),
            context=payload.get("context"),
            session_id=payload.get("session_id"),
        )


def build_dify_tools(system: Any) -> Dict[str, BaseDifyTool]:
    return {
        "router_tool": RouterTool("router_tool", "Route the query to the proper workflow.", system),
        "planner_tool": PlannerTool("planner_tool", "Plan sub-tasks and recommended tools.", system),
        "retriever_tool": RetrieverTool("retriever_tool", "Retrieve supporting documents and tool outputs.", system),
        "generator_tool": GeneratorTool("generator_tool", "Generate an answer from retrieved context.", system),
        "critic_tool": CriticTool("critic_tool", "Evaluate answer quality and suggest revision.", system),
        "agentic_rag_query": AgenticRAGQueryTool("agentic_rag_query", "Run the full AgenticRAG pipeline.", system),
    }

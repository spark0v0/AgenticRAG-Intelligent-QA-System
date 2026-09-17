from __future__ import annotations

import asyncio
import time
import uuid
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentInput, AgentOutput
from agents.critic import Critic
from agents.generator import Generator
from agents.planner import Planner
from agents.retriever import Retriever
from agents.router import Router
from integrations.langchain_adapter import build_langchain_runnable
from memory.sqlite_memory import SessionMemory
from models import build_model_client
from utils.execution import Execution, current_execution, public_data


class AgenticRAGSystem:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        model_cfg = config.get("model", {})
        self.model_profiles = self._build_model_profiles(model_cfg, config.get("model_profiles", []))
        self.default_model_profile = self._default_profile_id(model_cfg)
        self.router = Router(config.get("router", {}), model_cfg)
        self.planner = Planner(config.get("planner", {}))
        self.retriever = Retriever(config.get("retriever", {}), config)
        self.generator = Generator(config.get("generator", {}), model_cfg)
        self.critic = Critic(config.get("critic", {}))
        self.max_retries = config.get("system", {}).get("max_retries", config.get("max_retries", 2))
        self.enable_visualization = config.get("system", {}).get(
            "enable_visualization", config.get("enable_visualization", True)
        )
        memory_path = config.get("system", {}).get("memory_path", "data/memory/sessions.json")
        self.memory = SessionMemory(Path(memory_path))
        self.execution_trace: List[Dict[str, Any]] = []
        self.langchain_runnable = build_langchain_runnable(self)
        self._cancel_events: Dict[str, asyncio.Event] = {}
        self._run_tasks: Dict[str, asyncio.Task] = {}
        self._session_runs: Dict[str, str] = {}
        self._verified_models: Dict[str, float] = {}

    def _reserve_run(self, query: str, session_id: str | None, run_id: str | None,
                     streaming: bool, listener=None) -> Execution:
        session_id = session_id or str(uuid.uuid4())
        run_id = run_id or str(uuid.uuid4())
        if session_id in self._session_runs:
            raise ValueError("当前会话仍在执行，请等待完成或停止后重试。")
        try:
            self.memory.start_run(run_id, session_id, query)
        except sqlite3.IntegrityError as exc:
            raise ValueError("运行编号重复或会话正在执行，请刷新后重试。") from exc
        self._session_runs[session_id] = run_id
        return Execution(session_id, run_id, streaming, self.memory.record_event, listener)

    def start_query(self, user_query: str, context=None, session_id=None, run_id=None, listener=None):
        execution = self._reserve_run(user_query, session_id, run_id, True, listener)
        self.memory.save_input(execution.run_id, execution.session_id, user_query,
                               self._build_attachment_records((context or {}).get("images", [])))
        task = asyncio.create_task(self._run_query(user_query, context, execution))
        self._run_tasks[execution.run_id] = task
        return execution, task

    async def query(self, user_query: str, context=None, session_id=None) -> Dict[str, Any]:
        execution = self._reserve_run(user_query, session_id, None, False)
        self.memory.save_input(execution.run_id, execution.session_id, user_query,
                               self._build_attachment_records((context or {}).get("images", [])))
        self._run_tasks[execution.run_id] = asyncio.current_task()
        return await self._run_query(user_query, context, execution)

    async def _run_query(self, user_query: str, context, execution: Execution) -> Dict[str, Any]:
        token = current_execution.set(execution)
        try:
            execution.emit("started", {"mode": "live"})
            result = await self._query(user_query, context, execution.session_id)
            result["run_id"] = execution.run_id
            result["execution_trace"] = self.memory.get_events(execution.session_id, execution.run_id)
            stored = {k: v for k, v in result.items() if k not in {"messages", "execution_trace", "capabilities", "_turn"}}
            self.memory.complete_run(execution.run_id, public_data(stored), public_data(result.pop("_turn")))
            if result.get("model_provider") in {"openai", "deepseek", "ollama", "xinference"}:
                self._verified_models[result["model_profile"]] = time.time()
            execution.emit("completed", {"result": {k: v for k, v in result.items()
                                                     if k not in {"messages", "execution_trace", "capabilities"}}})
            return result
        except asyncio.CancelledError:
            self.memory.finish_run(execution.run_id, "cancelled", public_data({"answer": execution.draft}))
            execution.emit("cancelled", {"message": "本轮执行已取消，已生成内容仅作为未完成草稿保留。"})
            raise
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else f"执行失败（{type(exc).__name__}），请检查模型与工具配置后重试。"
            message = public_data(message)
            self.memory.finish_run(execution.run_id, "error", public_data({"answer": execution.draft}), message)
            execution.emit("error", {"message": message})
            raise
        finally:
            self._run_tasks.pop(execution.run_id, None)
            if self._session_runs.get(execution.session_id) == execution.run_id:
                self._session_runs.pop(execution.session_id, None)
            self._cancel_events.pop(execution.session_id, None)
            current_execution.reset(token)

    def cancel_run(self, run_id: str) -> bool:
        task = self._run_tasks.get(run_id)
        if task is None or task.done() or task.cancelling():
            return False
        task.cancel()
        return True

    async def _query(
        self,
        user_query: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        session_id = session_id or str(uuid.uuid4())
        context = dict(context or {})
        selected_profile = self._resolve_model_profile(context.get("model_profile") or context.get("model_profile_id"))
        context["model_profile"] = selected_profile["id"]
        context["model_config"] = selected_profile["config"]
        images = self._normalize_images(context.get("images") or context.get("attachments") or [])
        if images:
            context["images"] = images
        if not user_query.strip() and images:
            user_query = "请描述这张图片。"
        history = self.memory.get_history(session_id)
        cancel_event = self._cancel_events.setdefault(session_id, asyncio.Event())
        cancel_event.clear()
        self._log_execution(session_id, "start", {"query": user_query})

        try:
            routing_result = await self.router.execute(
                AgentInput(query=user_query, context=context, history=history, session_id=session_id)
            )
            self._log_execution(session_id, "routing", routing_result.metadata)
            self._ensure_not_cancelled(session_id)

            if routing_result.metadata["route"] == "planning":
                result = await self._execute_planning_flow(user_query, context, history, session_id, routing_result.metadata)
            elif routing_result.metadata["route"] == "retrieval":
                result = await self._execute_retrieval_flow(user_query, context, history, session_id, routing_result.metadata)
            else:
                result = await self._execute_direct_flow(user_query, context, history, session_id, routing_result.metadata)

            result["routing"] = routing_result.metadata
            execution = current_execution.get()
            result["run_id"] = execution.run_id if execution else None
            result["_turn"] = {
                    "query": user_query,
                    "run_id": result["run_id"],
                    "result": public_data({k: v for k, v in result.items() if k not in {"messages", "_turn"}}),
                    "response": result.get("answer", ""),
                    "timestamp": time.time(),
                    "route": routing_result.metadata.get("route"),
                    "intent": routing_result.metadata.get("intent"),
                    "response_mode": result.get("response_mode"),
                    "model_profile": selected_profile["id"],
                    "attachments": self._build_attachment_records(images),
                    "image_count": len(images),
                    "tool_errors": result.get("tool_errors") or [],
                    "model_error": result.get("model_error"),
                }
            self._log_execution(session_id, "complete", {"status": "success"})
        except asyncio.CancelledError:
            self._log_execution(session_id, "cancelled", {"status": "cancelled"})
            raise

        session_history = [*self.memory.get_session(session_id), result["_turn"]]
        result["messages"] = self._build_messages(session_history)
        result["session_title"] = self._build_session_title(session_history)
        result["turn_count"] = len(session_history)
        result["image_count"] = len(images)
        result["model_profile"] = selected_profile["id"]
        result["capabilities"] = self.build_capability_report()
        if self.enable_visualization:
            result["execution_trace"] = self._generate_execution_trace(session_id)
        return result

    async def _execute_direct_flow(
        self,
        query: str,
        context: Optional[Dict[str, Any]],
        history: List[Dict[str, Any]],
        session_id: str,
        routing: Dict[str, Any],
    ) -> Dict[str, Any]:
        generation = await self.generator.execute(
            AgentInput(
                query=query,
                context={**(context or {}), "response_mode": routing.get("response_mode", "chat"), "intent": routing.get("intent")},
                history=history,
                session_id=session_id,
            )
        )
        self._log_execution(session_id, "generation", generation.metadata)
        critique = await self._critique_and_revise(
            query,
            generation,
            [],
            history,
            session_id,
            images=(context or {}).get("images", []),
            model_config=(context or {}).get("model_config"),
            model_profile=(context or {}).get("model_profile"),
        )
        return self._build_result(session_id, critique["generation"], critique["critic"], "direct")

    async def _execute_retrieval_flow(
        self,
        query: str,
        context: Optional[Dict[str, Any]],
        history: List[Dict[str, Any]],
        session_id: str,
        routing: Dict[str, Any],
    ) -> Dict[str, Any]:
        retrieval = await self.retriever.execute(
            AgentInput(
                query=query,
                context={**(context or {}), "intent": routing.get("intent"), "response_mode": routing.get("response_mode")},
                history=history,
                session_id=session_id,
            )
        )
        self._log_execution(session_id, "retrieval", retrieval.metadata)
        self._ensure_not_cancelled(session_id)
        generation = await self.generator.execute(
            AgentInput(
                query=query,
                context={
                    "documents": retrieval.metadata.get("documents", []),
                    "retrieval_plan": retrieval.metadata.get("retrieval_plan", {}),
                    "tool_calls": retrieval.metadata.get("tool_calls", []),
                    "images": (context or {}).get("images", []),
                    "model_config": (context or {}).get("model_config"),
                    "model_profile": (context or {}).get("model_profile"),
                    "response_mode": retrieval.metadata.get("response_mode") or routing.get("response_mode"),
                    "intent": retrieval.metadata.get("intent") or routing.get("intent"),
                },
                history=history,
                session_id=session_id,
            )
        )
        self._log_execution(session_id, "generation", generation.metadata)
        critique = await self._critique_and_revise(
            query,
            generation,
            retrieval.metadata.get("documents", []),
            history,
            session_id,
            images=(context or {}).get("images", []),
            model_config=(context or {}).get("model_config"),
            model_profile=(context or {}).get("model_profile"),
        )
        result = self._build_result(session_id, critique["generation"], critique["critic"], "retrieval")
        result["retrieval_quality"] = retrieval.metadata.get("retrieval_quality")
        result["retrieval_plan"] = retrieval.metadata.get("retrieval_plan")
        result["tool_calls"] = retrieval.metadata.get("tool_calls")
        result["tool_errors"] = retrieval.metadata.get("tool_errors")
        return result

    async def _execute_planning_flow(
        self,
        query: str,
        context: Optional[Dict[str, Any]],
        history: List[Dict[str, Any]],
        session_id: str,
        routing: Dict[str, Any],
    ) -> Dict[str, Any]:
        plan_context = {
            **(context or {}),
            "intent": routing.get("intent"),
            "complexity": routing.get("complexity"),
        }
        plan = await self.planner.execute(
            AgentInput(query=query, context=plan_context, history=history, session_id=session_id)
        )
        self._log_execution(session_id, "planning", plan.metadata)
        self._ensure_not_cancelled(session_id)
        retrieval_context = {
            "tools": plan.metadata.get("recommended_tools", []),
            "strategy": plan.metadata.get("strategy"),
            "intent": plan.metadata.get("intent"),
            "response_mode": "analysis",
        }
        retrieval = await self.retriever.execute(
            AgentInput(
                query=plan.metadata.get("rewritten_query", query),
                context=retrieval_context,
                history=history,
                session_id=session_id,
            )
        )
        self._log_execution(session_id, "retrieval", retrieval.metadata)
        self._ensure_not_cancelled(session_id)
        generation = await self.generator.execute(
            AgentInput(
                query=query,
                context={
                    "documents": retrieval.metadata.get("documents", []),
                    "tasks": plan.metadata.get("tasks", []),
                    "retrieval_plan": retrieval.metadata.get("retrieval_plan", {}),
                    "tool_calls": retrieval.metadata.get("tool_calls", []),
                    "images": (context or {}).get("images", []),
                    "model_config": (context or {}).get("model_config"),
                    "model_profile": (context or {}).get("model_profile"),
                    "response_mode": "analysis",
                    "intent": plan.metadata.get("intent") or routing.get("intent"),
                },
                history=history,
                session_id=session_id,
            )
        )
        self._log_execution(session_id, "generation", generation.metadata)
        critique = await self._critique_and_revise(
            query,
            generation,
            retrieval.metadata.get("documents", []),
            history,
            session_id,
            images=(context or {}).get("images", []),
            model_config=(context or {}).get("model_config"),
            model_profile=(context or {}).get("model_profile"),
        )
        result = self._build_result(session_id, critique["generation"], critique["critic"], "planning")
        result["task_breakdown"] = plan.metadata.get("tasks", [])
        result["rewritten_query"] = plan.metadata.get("rewritten_query", query)
        result["resource_plan"] = plan.metadata.get("resource_plan", {})
        result["retrieval_quality"] = retrieval.metadata.get("retrieval_quality")
        result["retrieval_plan"] = retrieval.metadata.get("retrieval_plan")
        result["tool_calls"] = retrieval.metadata.get("tool_calls")
        result["tool_errors"] = retrieval.metadata.get("tool_errors")
        return result

    async def _critique_and_revise(
        self,
        query: str,
        generation: AgentOutput,
        documents: List[Dict[str, Any]],
        history: List[Dict[str, Any]],
        session_id: str,
        images: Optional[List[Dict[str, Any]]] = None,
        model_config: Optional[Dict[str, Any]] = None,
        model_profile: Optional[str] = None,
    ) -> Dict[str, AgentOutput]:
        images = images or []
        critic = await self.critic.execute(
            AgentInput(
                query=query,
                context={"content": generation.content, "documents": documents, "mode": generation.metadata.get("response_mode")},
                history=history,
                session_id=session_id,
            )
        )
        self._log_execution(session_id, "critic", critic.metadata)
        current_generation = generation
        retries = 0
        while critic.metadata.get("need_revision") and retries < self.max_retries:
            self._ensure_not_cancelled(session_id)
            retries += 1
            self._log_execution(session_id, f"revision_{retries}", critic.metadata)
            current_generation = await self.generator.execute(
                AgentInput(
                    query=query,
                    context={
                        "documents": documents,
                        "critique": critic.metadata,
                        "response_mode": generation.metadata.get("response_mode"),
                        "images": images,
                        "model_config": model_config,
                        "model_profile": model_profile,
                    },
                    history=history,
                    session_id=session_id,
                )
            )
            critic = await self.critic.execute(
                AgentInput(
                    query=query,
                    context={
                        "content": current_generation.content,
                        "documents": documents,
                        "mode": current_generation.metadata.get("response_mode"),
                    },
                    history=history,
                    session_id=session_id,
                )
            )
            self._log_execution(session_id, f"critic_revision_{retries}", critic.metadata)
        return {"generation": current_generation, "critic": critic}

    def _build_result(
        self,
        session_id: str,
        generation: AgentOutput,
        critic: AgentOutput,
        route: str,
    ) -> Dict[str, Any]:
        return {
            "answer": generation.content,
            "confidence": generation.confidence,
            "sources": generation.metadata.get("sources", []),
            "source_map": generation.metadata.get("source_map", []),
            "reasoning": f"Completed via {route} route.",
            "session_id": session_id,
            "evaluation_score": critic.metadata.get("score"),
            "model": generation.metadata.get("model_name"),
            "model_provider": generation.metadata.get("provider"),
            "model_profile": generation.metadata.get("model_profile"),
            "model_error": generation.metadata.get("model_error"),
            "response_mode": generation.metadata.get("response_mode"),
            "critic_feedback": critic.metadata.get("feedback"),
            "critic_suggestions": critic.metadata.get("suggestions", []),
        }

    def cancel_session(self, session_id: str) -> bool:
        run_id = self._session_runs.get(session_id)
        if run_id:
            return self.cancel_run(run_id)
        event = self._cancel_events.get(session_id)
        if not event:
            return False
        event.set()
        return True

    def _ensure_not_cancelled(self, session_id: str) -> None:
        event = self._cancel_events.get(session_id)
        if event and event.is_set():
            raise asyncio.CancelledError(f"Session {session_id} was cancelled.")

    def _log_execution(self, session_id: str, step: str, data: Dict[str, Any]) -> None:
        execution = current_execution.get()
        if execution:
            execution.emit("info", {"step": step, "summary": data})
            return
        self.execution_trace.append(
            {
                "session_id": session_id,
                "step": step,
                "data": data,
                "timestamp": time.time(),
            }
        )

    def _generate_execution_trace(self, session_id: str) -> List[Dict[str, Any]]:
        return self.memory.get_events(session_id)

    def get_session_detail(self, session_id: str) -> Dict[str, Any]:
        history = self.memory.get_session(session_id)
        return {
            "session_id": session_id,
            "session_title": self._build_session_title(history),
            "turn_count": len(history),
            "messages": self._build_messages(history),
            "trace": self._generate_execution_trace(session_id),
            "runs": self.memory.list_runs(session_id),
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        sessions = self.memory.list_sessions()
        for item in sessions:
            history = self.memory.get_session(item["session_id"])
            item["session_title"] = self._build_session_title(history) if history else item["preview"][:24]
        return sessions

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "protocol": tool.protocol,
                "tags": tool.tags,
                "timeout_seconds": tool.timeout_seconds,
                "schema": tool.input_schema,
            }
            for tool in self.retriever.registry.list_tools()
        ]

    def list_model_profiles(self) -> List[Dict[str, Any]]:
        return [self._sanitize_model_profile(profile) for profile in self.model_profiles.values()]

    def build_capability_report(self) -> List[Dict[str, Any]]:
        tools = list(self.retriever.registry.list_tools())
        protocols = {tool.protocol for tool in tools}
        tool_names = {tool.name for tool in tools}
        has_vector = "knowledge_base_search" in tool_names
        has_graph = "knowledge_graph_search" in tool_names
        has_mcp = "mcp" in protocols
        has_function_calling = bool({"function_calling"}.intersection(protocols)) or self.generator.model_client.supports_function_calling
        has_live_data = {"web_search", "weather_lookup"}.intersection(tool_names)

        return [
            {
                "title": "多智能体架构",
                "status": "met",
                "status_label": "已具备",
                "note": "Router、Planner、Retriever、Generator、Critic 已形成闭环主流程。",
            },
            {
                "title": "查询理解与任务分解",
                "status": "met",
                "status_label": "已具备",
                "note": "支持意图识别、复杂度评估、查询改写、任务拆解和资源规划。",
            },
            {
                "title": "工具使用与扩展",
                "status": "met" if has_mcp and has_function_calling else "partial",
                "status_label": "已具备" if has_mcp and has_function_calling else "部分满足",
                "note": f"当前工具协议覆盖：{', '.join(sorted(protocols)) or '无'}；支持参数校验、超时控制和统一结果格式。",
            },
            {
                "title": "多源检索与动态决策",
                "status": "met" if has_vector and has_graph and has_live_data else "partial",
                "status_label": "已具备" if has_vector and has_graph and has_live_data else "部分满足",
                "note": "支持本地向量知识库、知识图谱、联网搜索、实时天气查询和自适应多轮检索。",
            },
            {
                "title": "答案评审与闭环优化",
                "status": "met",
                "status_label": "已具备",
                "note": "Critic 会对答案进行打分，并在复杂问题中触发多轮修订。",
            },
            {
                "title": "对话管理与执行可视化",
                "status": "met",
                "status_label": "已具备",
                "note": "支持会话短期记忆、执行轨迹、来源追踪和会话取消。",
            },
            {
                "title": "LangChain 集成",
                "status": "met" if self.langchain_runnable is not None else "partial",
                "status_label": "已具备" if self.langchain_runnable is not None else "部分满足",
                "note": "系统可作为 LangChain Runnable 使用，并统一暴露 AgenticRAG 查询入口。",
            },
        ]

    def system_status(self) -> Dict[str, Any]:
        realtime_tools = [tool["name"] for tool in self.list_tools() if "realtime" in (tool.get("tags") or [])]
        default_profile = self.model_profiles.get(self.default_model_profile, {})
        default_cfg = default_profile.get("config", {})
        model_client = build_model_client(default_cfg)
        return {
            "status": "running",
            "mode": "live",
            "connection_verified": self.default_model_profile in self._verified_models,
            "image_limits": {"count": 4, "bytes": 4 * 1024 * 1024},
            "model_provider": default_cfg.get("provider") or self.config.get("model", {}).get("provider", ""),
            "model_name": default_cfg.get("model_name") or self.config.get("model", {}).get("model_name"),
            "model_ready": model_client.is_available,
            "default_model_profile": self.default_model_profile,
            "model_profiles": self.list_model_profiles(),
            "agents": ["router", "planner", "retriever", "generator", "critic"],
            "tools": self.list_tools(),
            "realtime_tools": realtime_tools,
            "langchain_runnable": self.langchain_runnable is not None,
            "capabilities": self.build_capability_report(),
        }

    def _build_messages(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        for turn in history:
            timestamp = turn.get("timestamp")
            messages.append(
                {
                "role": "user",
                "content": turn.get("query", ""),
                "timestamp": timestamp,
                "attachments": turn.get("attachments", []),
                "id": f"{turn.get('run_id') or timestamp}-user",
                "run_id": turn.get("run_id"),
            }
        )
            messages.append(
                {
                    "role": "assistant",
                    "content": turn.get("response", ""),
                    "timestamp": timestamp,
                    "id": f"{turn.get('run_id') or timestamp}-assistant",
                    "run_id": turn.get("run_id"),
                    "result": turn.get("result"),
                    "status": "success",
                }
            )
        return messages

    def _build_session_title(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return "新会话"
        first_query = (history[0].get("query") or "").strip()
        return first_query[:24] + ("..." if len(first_query) > 24 else "")

    def _build_model_profiles(self, model_cfg: Dict[str, Any], configured_profiles: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        profiles: Dict[str, Dict[str, Any]] = {}
        for item in configured_profiles or []:
            if not isinstance(item, dict):
                continue
            profile_id = str(item.get("id") or item.get("model_name") or "").strip()
            if not profile_id:
                continue
            cfg = {key: value for key, value in item.items() if key not in {"id", "label"}}
            profiles[profile_id] = {
                "id": profile_id,
                "label": item.get("label") or profile_id,
                "config": cfg,
            }

        if not profiles:
            profiles["default"] = {
                "id": "default",
                "label": model_cfg.get("model_name", "default"),
                "config": dict(model_cfg),
            }
        return profiles

    def _default_profile_id(self, model_cfg: Dict[str, Any]) -> str:
        configured = self.config.get("default_model_profile")
        if configured and configured in self.model_profiles:
            return str(configured)
        for profile_id, profile in self.model_profiles.items():
            cfg = profile["config"]
            if cfg.get("provider") == model_cfg.get("provider") and cfg.get("model_name") == model_cfg.get("model_name"):
                return profile_id
        return next(iter(self.model_profiles))

    def _resolve_model_profile(self, profile_id: Any) -> Dict[str, Any]:
        key = str(profile_id or self.default_model_profile).strip()
        return self.model_profiles.get(key) or self.model_profiles[self.default_model_profile]

    def _sanitize_model_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        cfg = profile.get("config", {})
        client = build_model_client(cfg)
        return {
            "id": profile.get("id"),
            "label": profile.get("label"),
            "provider": cfg.get("provider"),
            "model_name": cfg.get("model_name"),
            "supports_vision": client.supports_vision,
            "configured": client.is_available,
            "connection_verified": profile["id"] in self._verified_models,
            "last_success_at": self._verified_models.get(profile["id"]),
            "supports_streaming": cfg.get("provider") in {"openai", "deepseek"} and cfg.get("supports_streaming", True),
            "api_key_env": cfg.get("api_key_env") or self._default_api_key_env(cfg.get("provider")),
        }

    def _default_api_key_env(self, provider: Any) -> str | None:
        return {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "ollama": "OLLAMA_API_KEY",
            "xinference": "XINFERENCE_API_KEY",
        }.get(str(provider or ""))

    def _normalize_images(self, images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for image in images[:4]:
            data_url = str(image.get("data_url") or image.get("url") or "").strip()
            if not data_url:
                continue
            normalized.append(
                {
                    "type": "image",
                    "filename": image.get("filename") or image.get("name") or "image",
                    "mime_type": image.get("mime_type") or image.get("mime") or "image/*",
                    "size": image.get("size"),
                    "data_url": data_url,
                }
            )
        return normalized

    def _build_attachment_records(self, images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "image",
                "filename": image.get("filename") or "image",
                "mime_type": image.get("mime_type") or "image/*",
                "size": image.get("size"),
                "data_url": image.get("data_url"),
            }
            for image in images
        ]


async def main() -> None:
    from utils.config import Config
    system = AgenticRAGSystem(Config().config)
    result = await system.query("请分析 AgenticRAG 系统需要哪些核心能力")
    print(result["answer"])


if __name__ == "__main__":
    asyncio.run(main())

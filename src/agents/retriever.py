from __future__ import annotations

import asyncio
import re
import json
from typing import Any, Dict, List, Tuple

from models import build_model_client
from retrieval.hybrid_store import retrieval_query
from tools.builtin import build_builtin_tools, is_code_like, tokenize
from tools.registry import ToolRegistry
from utils.execution import current_execution

from .base_agent import AgentInput, AgentOutput, BaseAgent


class Retriever(BaseAgent):
    def __init__(self, config: Dict[str, Any], system_config: Dict[str, Any] | None = None):
        super().__init__("Retriever", config)
        self.max_attempts = config.get("max_attempts", 3)
        self.max_results = config.get("max_results", 8)
        self.quality_threshold = config.get("quality_threshold", 0.62)
        self.default_strategy = config.get("default_strategy", "parallel")
        self.max_selected_tools = config.get("max_selected_tools", 3)
        self.system_config = system_config or {"retrieval": config}
        self.model_client = build_model_client((self.system_config or {}).get("model", {}))
        self.registry = ToolRegistry(default_timeout_seconds=float(config.get("tool_timeout_seconds", 15)))
        for tool in build_builtin_tools(self.system_config):
            self.registry.register(tool)

    async def process(self, input_data: AgentInput) -> AgentOutput:
        if not self.validate_input(input_data):
            raise ValueError("Invalid input data")

        query = retrieval_query(input_data.query)
        context = input_data.context or {}
        intent = self._infer_intent(query, context)
        strategy = str(context.get("strategy") or self.default_strategy)
        selected_tools, selector_meta = await self._select_tools(query, intent, context)

        all_documents: List[Dict[str, Any]] = []
        tool_calls: List[Dict[str, Any]] = []
        query_variants: List[str] = []
        latest_quality = 0.0
        executed = set()
        stop_reason = "budget_exhausted"
        budget = max(1, min(self.max_attempts, int(context.get("retrieval_rounds", 2))))
        planned_queries = list(dict.fromkeys(context.get("search_queries") or [query]))[:3]

        for attempt in range(budget):
            execution = current_execution.get()
            if execution:
                execution.emit("retrieval_round", {"round": attempt + 1, "strategy": strategy})
            variant = self._rewrite_for_retrieval(query, intent, attempt, query_variants)
            if variant in query_variants:
                stop_reason = "duplicate_query"
                break
            query_variants.append(variant)
            round_plan = []
            for search_query in (planned_queries if attempt == 0 else [variant]):
                for step in self._build_round_plan(search_query, intent, selected_tools, context):
                    identity = json.dumps(step, sort_keys=True, ensure_ascii=False)
                    if identity not in executed:
                        executed.add(identity)
                        round_plan.append(step)
            if not round_plan:
                stop_reason = "duplicate_query"
                break
            round_documents, round_calls = await self._execute_round(round_plan, strategy)
            previous_count = len(self._rank_results(query, all_documents, intent))
            all_documents.extend(round_documents)
            tool_calls.extend(round_calls)
            ranked = self._rank_results(query, all_documents, intent)[: self.max_results]
            latest_quality = self._assess_quality(ranked, intent)
            if ranked and (intent in {"math", "weather", "web_search"} or latest_quality >= self.quality_threshold):
                stop_reason = "sufficient_evidence"
                break
            if round_calls and all(call["status"] != "success" for call in round_calls):
                stop_reason = "tools_unavailable"
                break
            if attempt and len(self._rank_results(query, all_documents, intent)) <= previous_count:
                stop_reason = "no_new_evidence"
                break

        ranked = self._rank_results(query, all_documents, intent)[: self.max_results]
        sources = [doc["source"] for doc in ranked]
        tool_errors = [call for call in tool_calls if call.get("status") != "success"]
        retrieval_plan = {
            "strategy": strategy,
            "selected_tools": selected_tools,
            "query_variants": query_variants,
            "selector": selector_meta,
            "search_scope": context.get("search_scope", "auto"),
            "knowledge_base_id": context.get("knowledge_base_id"),
            "library_states": [call.get("metadata", {}).get("state", "error") for call in tool_calls if call["tool"] == "library_search"],
            "search_queries": planned_queries,
            "round_budget": budget,
            "stop_reason": stop_reason,
        }

        return AgentOutput(
            content=f"Retrieved {len(ranked)} supporting document(s).",
            metadata={
                "documents": ranked,
                "sources": sources,
                "retrieval_plan": retrieval_plan,
                "tool_calls": tool_calls,
                "tool_errors": tool_errors,
                "tool_count": len(selected_tools),
                "intent": intent,
                "retrieval_quality": latest_quality,
                "attempt_count": len(query_variants),
                "response_mode": self._response_mode(intent, ranked, tool_calls),
            },
            confidence=self._calculate_confidence(ranked, latest_quality),
        )

    def _infer_intent(self, query: str, context: Dict[str, Any]) -> str:
        if context.get("intent"):
            return str(context["intent"])
        lowered = query.lower()
        if any(token in lowered for token in ["天气", "气温", "温度", "下雨", "weather", "forecast"]):
            return "weather"
        if any(token in lowered for token in ["最新", "搜索", "查一下", "帮我查", "新闻", "官网", "网页", "互联网", "web"]):
            return "web_search"
        if any(token in lowered for token in ["代码", "code", "python", "bug", "函数"]):
            return "code"
        if any(token in lowered for token in ["分析", "比较", "区别", "原理", "流程", "架构"]):
            return "analysis"
        if any(token in lowered for token in ["能力", "支持", "协议", "mcp", "langchain"]):
            return "capability"
        if any(symbol in query for symbol in ["+", "-", "*", "/"]):
            return "math"
        return "fact"

    async def _select_tools(self, query: str, intent: str, context: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
        if context.get("knowledge_base_id"):
            tools = ["library_search"]
            if context.get("search_scope") == "all":
                tools.append("web_search")
            return tools, {"mode": "knowledge_library", "knowledge_base_id": context["knowledge_base_id"], "used_function_calling": False}
        scope_tools = {"local": ["knowledge_base_search", "knowledge_graph_search"],
                       "web": ["web_search"], "all": ["knowledge_base_search", "web_search"]}
        scope = context.get("search_scope", "auto")
        if scope in scope_tools:
            return scope_tools[scope], {"mode": "user_scope", "used_function_calling": False}
        hinted_tools = [tool for tool in context.get("tools") or [] if self.registry.get(tool)]
        if hinted_tools:
            return hinted_tools[: self.max_selected_tools], {"mode": "planner_hint", "used_function_calling": False}

        if self.config.get("tool_selection", "policy") != "model":
            return self._fallback_tools(intent)[:self.max_selected_tools], {
                "mode": "intent_policy", "used_function_calling": False}

        available_schemas = self.registry.export_function_schemas()
        model_config = context.get("model_config")
        selector = build_model_client(model_config) if model_config else self.model_client
        try:
            selection = await asyncio.wait_for(
                selector.select_tools(query, available_schemas, max_tools=self.max_selected_tools),
                float(self.config.get("selector_timeout_seconds", 5)))
        except (TimeoutError, ValueError):
            return self._fallback_tools(intent), {"mode": "policy_after_selector_failure", "used_function_calling": False}
        selected = [name for name in selection.tool_names if self.registry.get(name)]
        if selected:
            return selected, {
                "mode": "function_calling" if selection.used_function_calling else "heuristic",
                "used_function_calling": selection.used_function_calling,
                "selector_provider": selection.provider,
                "selector_model": selection.model_name,
                "raw_response": selection.raw_response,
            }

        fallback = self._fallback_tools(intent)
        return fallback, {"mode": "fallback", "used_function_calling": False}

    def _fallback_tools(self, intent: str) -> List[str]:
        if intent == "math":
            return ["calculator"]
        if intent == "weather":
            return ["weather_lookup"]
        if intent == "web_search":
            return ["web_search"]
        if intent == "capability":
            return ["knowledge_base_search"]
        if intent == "analysis":
            return ["knowledge_base_search", "knowledge_graph_search"]
        return ["knowledge_base_search", "knowledge_graph_search"]

    def _rewrite_for_retrieval(self, query: str, intent: str, attempt: int, previous: List[str]) -> str:
        if attempt == 0:
            return query
        # Retry with a shorter lexical query rather than repeatedly adding generic terms.
        terms = [term for term in tokenize(query) if len(term) > 1]
        compact = " ".join(dict.fromkeys(terms))[:300]
        return compact or query

    def _build_round_plan(
        self,
        query: str,
        intent: str,
        tools: List[str],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        include_code = intent == "code"
        prefer_documents = intent != "code"
        retrieval_mode = context.get("retrieval_mode", "hybrid")
        plan: List[Dict[str, Any]] = []
        for tool_name in tools:
            if tool_name == "calculator":
                payload: Dict[str, Any] = {"expression": query}
            elif tool_name == "weather_lookup":
                payload = {"query": query, "location": context.get("location") or self._extract_location(query), "days": 1}
            elif tool_name == "web_search":
                payload = {"query": query, "limit": min(self.max_results, 5)}
            elif tool_name == "library_search":
                payload = {"query": query, "knowledge_base_id": context["knowledge_base_id"], "limit": self.max_results}
            elif tool_name == "knowledge_base_search":
                payload = {
                    "query": query,
                    "limit": self.max_results,
                    "include_code": include_code,
                    "prefer_documents": prefer_documents,
                    "retrieval_mode": retrieval_mode,
                }
            elif tool_name == "project_capability_lookup":
                payload = {"query": query, "limit": min(self.max_results, 4)}
            else:
                payload = {"query": query, "limit": self.max_results}
            plan.append({"tool": tool_name, "payload": payload})
        return plan

    async def _execute_round(self, plan: List[Dict[str, Any]], strategy: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        semaphore = asyncio.Semaphore(3)

        async def _run(step: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
            tool_name = step["tool"]
            try:
                async with semaphore:
                    result = await self.registry.invoke(tool_name, step["payload"])
                metadata = result.get("metadata", {})
                status = result.get("status", "success")
                documents = result.get("documents", []) if status == "success" else []
                return documents, {
                    "tool": tool_name,
                    "status": status,
                    "error": result.get("error"),
                    "document_count": len(documents),
                    "metadata": metadata,
                }
            except Exception as exc:
                return [], {
                    "tool": tool_name,
                    "status": "error",
                    "error": str(exc),
                    "document_count": 0,
                    "metadata": {},
                }

        if strategy == "sequential":
            documents: List[Dict[str, Any]] = []
            calls: List[Dict[str, Any]] = []
            for step in plan:
                round_documents, call = await _run(step)
                documents.extend(round_documents)
                calls.append(call)
                if call["status"] == "success" and round_documents:
                    continue
            return documents, calls

        results = await asyncio.gather(*[_run(step) for step in plan])
        documents: List[Dict[str, Any]] = []
        calls: List[Dict[str, Any]] = []
        for round_documents, call in results:
            documents.extend(round_documents)
            calls.append(call)
        return documents, calls

    def _rank_results(self, query: str, documents: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
        query_terms = set(tokenize(query))
        ranked: List[Dict[str, Any]] = []
        seen = set()
        for doc in documents:
            content = doc.get("content", "")
            fingerprint = (doc.get("metadata") or {}).get("chunk_id") or (doc.get("source"), content[:180])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)

            doc_terms = set(tokenize(content))
            overlap = len(query_terms.intersection(doc_terms))
            base_score = doc.get("score") or doc.get("similarity") or doc.get("relevance") or doc.get("confidence") or 0.0
            score = float(base_score)
            source = str(doc.get("source", ""))
            metadata = doc.get("metadata") or {}

            if intent != "code" and is_code_like(content, source):
                score -= 0.18
            if source == "calculator":
                score += 0.28
            if source == "weather_lookup":
                score += 0.26
            if metadata.get("provider") in {"duckduckgo_instant", "wikipedia"} or metadata.get("service") == "web":
                score += 0.2
            if metadata.get("protocol") == "mcp" and intent == "capability":
                score += 0.18

            enriched = dict(doc)
            enriched["score"] = round(max(min(score, 1.0), 0.0), 4)
            ranked.append(enriched)

        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked

    def _assess_quality(self, documents: List[Dict[str, Any]], intent: str) -> float:
        if not documents:
            return 0.0
        if intent in {"math", "weather"} and documents[0].get("score", 0.0) >= 0.9:
            return 0.94
        top_docs = documents[: min(4, len(documents))]
        avg_score = sum(doc.get("score", 0.0) for doc in top_docs) / len(top_docs)
        return round(min(avg_score, 1.0), 4)

    def _calculate_confidence(self, documents: List[Dict[str, Any]], quality: float) -> float:
        if not documents:
            return 0.0
        return round(min(quality + min(len(documents), 5) * 0.04, 0.98), 4)

    def _response_mode(self, intent: str, documents: List[Dict[str, Any]], tool_calls: List[Dict[str, Any]]) -> str:
        if intent == "math":
            return "math_tool"
        if intent == "weather":
            if documents:
                return "weather_tool"
            return "live_data_notice"
        if intent == "web_search":
            if documents:
                return "grounded"
            return "live_data_notice"
        if intent == "analysis":
            return "analysis"
        return "grounded"

    def _extract_location(self, query: str) -> str:
        match = re.search(r"(?:今天|明天|后天|现在|当前|最近)?([A-Za-z\u4e00-\u9fff·\-\s]{2,24}?)(?:的)?天气", query)
        candidate = match.group(1) if match else query.replace("天气", "")
        for token in ["帮我查", "查一下", "看看", "告诉我", "查询", "今天", "明天", "后天", "现在", "当前", "最近", "的", "怎么样", "如何"]:
            candidate = candidate.replace(token, "")
        candidate = candidate.strip(" ，。?？")
        return candidate or "北京"

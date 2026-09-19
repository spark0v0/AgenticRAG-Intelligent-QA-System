from __future__ import annotations

from typing import Any, Dict, List
import asyncio
import json
import re
from pydantic import BaseModel, Field, ValidationError
from models import build_model_client

from .base_agent import AgentInput, AgentOutput, BaseAgent


class SearchPlan(BaseModel):
    rewritten_query: str = Field(min_length=1, max_length=600)
    search_queries: list[str] = Field(min_length=1, max_length=3)

    # Independent evidence questions; generation remains the dependent final step.


class Planner(BaseAgent):
    VALID_INTENTS = {"fact", "analysis", "code", "math", "weather", "web_search", "capability", "chat", "vision"}

    def __init__(self, config: Dict[str, Any]):
        super().__init__("Planner", config)
        self.max_tasks = config.get("max_tasks", 8)
        self.complexity_threshold = config.get("complexity_threshold", 0.55)

    async def process(self, input_data: AgentInput) -> AgentOutput:
        if not self.validate_input(input_data):
            raise ValueError("Invalid input data")

        query = input_data.query.strip()
        context = input_data.context or {}
        rewritten_query = self._rewrite_query(query, input_data.history)
        intent = self._resolve_intent(query, context)
        complexity = self._resolve_complexity(query, context)
        tasks = self._build_tasks(rewritten_query, intent, complexity)
        search_queries = [rewritten_query]
        planning_source = "bounded_template"
        if self.config.get("use_llm", True) and context.get("model_config") and complexity >= self.complexity_threshold:
            cfg = {**context["model_config"], "max_tokens": 500, "temperature": 0}
            timeout = float(self.config.get("timeout_seconds", 8))
            try:
                client = build_model_client(cfg)
                if client.is_available:
                    response = await asyncio.wait_for(client.generate(
                        "你是检索规划器。仅输出 JSON，包含 rewritten_query 和 search_queries。"
                        "根据当前问题和最近问题消解指代；拆成1至3个可独立检索的具体问题。"
                        "保留实体、时间和约束，不编造答案，不输出思维链。",
                        json.dumps({"query": query, "knowledge_base_id": context.get("knowledge_base_id"), "search_scope": context.get("search_scope"), "previous_question": (input_data.history or [{}])[-1].get("query", "")[:600]}, ensure_ascii=False)), timeout)
                    raw = response.content.strip()
                    if raw.startswith("```"):
                        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
                    parsed = SearchPlan.model_validate_json(raw)
                    if response.error or any(not q.strip() or len(q) > 600 for q in parsed.search_queries):
                        raise ValueError("Invalid search plan")
                    rewritten_query = parsed.rewritten_query
                    search_queries = list(dict.fromkeys(q.strip() for q in parsed.search_queries))
                    planning_source = "structured_model"
            except (TimeoutError, ValueError, ValidationError):
                planning_source = "template_after_model_failure"
        strategy = "parallel"
        estimated_time = sum(task["estimated_seconds"] for task in tasks)
        recommended_tools = sorted({tool for task in tasks for tool in task["tools"]})
        if planning_source == "structured_model":
            tasks = [{"id": f"search_{i + 1}", "type": "retrieval", "description": question,
                      "dependencies": [], "tools": recommended_tools}
                     for i, question in enumerate(search_queries)]
            tasks.append({"id": "synthesize", "type": "generation", "description": "综合子问题证据并回答原问题",
                          "dependencies": [task["id"] for task in tasks], "tools": []})
        resource_plan = {
            "estimated_seconds": estimated_time,
            "tool_budget": len(recommended_tools),
            "retrieval_rounds": 2 if complexity >= self.complexity_threshold else 1,
            "model_tier": "heavy" if complexity >= self.complexity_threshold else "light",
        }

        return AgentOutput(
            content=f"已规划 {len(tasks)} 个任务，策略为 {strategy}。",
            metadata={
                "rewritten_query": rewritten_query,
                "intent": intent,
                "complexity": round(complexity, 4),
                "tasks": tasks,
                "strategy": strategy,
                "recommended_tools": recommended_tools,
                "estimated_seconds": estimated_time,
                "resource_plan": resource_plan,
                "response_mode": "analysis",
                "planning_source": planning_source,
                "search_queries": search_queries,
                "estimate_kind": "static_budget_not_measured",
            },
            confidence=min(0.62 + complexity * 0.3, 0.96),
        )

    def _resolve_intent(self, query: str, context: Dict[str, Any]) -> str:
        hinted_intent = str(context.get("intent") or "").strip()
        if hinted_intent in self.VALID_INTENTS:
            return hinted_intent
        return self._classify_intent(query)

    def _resolve_complexity(self, query: str, context: Dict[str, Any]) -> float:
        try:
            hinted_complexity = float(context.get("complexity"))
            return max(0.0, min(hinted_complexity, 1.0))
        except (TypeError, ValueError):
            return self._analyze_complexity(query)

    def _rewrite_query(self, query: str, history: List[Dict[str, Any]]) -> str:
        if history:
            recent_topic = history[-1].get("query", "").strip()
            if recent_topic and len(query) < 80 and re.search(r"它|这个|上述|刚才|继续|那[么个]|其", query):
                return f"{query}（结合上轮问题：{recent_topic}）"
        return query

    def _classify_intent(self, query: str) -> str:
        lowered = query.lower()
        if any(token in lowered for token in ["天气", "气温", "温度", "下雨", "weather", "forecast"]):
            return "weather"
        if any(token in lowered for token in ["最新", "搜索", "查一下", "帮我查", "新闻", "官网", "网页", "互联网", "web"]):
            return "web_search"
        if any(token in lowered for token in ["代码", "code", "python", "bug", "函数"]):
            return "code"
        if any(token in lowered for token in ["比较", "分析", "区别", "explain", "analyze", "架构"]):
            return "analysis"
        if any(token in lowered for token in ["能力", "支持", "协议", "mcp", "langchain"]):
            return "capability"
        if any(token in lowered for token in ["多少", "计算", "+", "-", "*", "/"]):
            return "math"
        return "fact"

    def _analyze_complexity(self, query: str) -> float:
        lowered = query.lower()
        signals = sum(
            1
            for token in ["分析", "比较", "区别", "原理", "推理", "步骤", "方案", "compare", "reason", "架构"]
            if token in lowered
        )
        punctuation = min(query.count("，") + query.count(",") + query.count("？") + query.count("?"), 3)
        length_factor = min(len(query) / 120, 1.0)
        return min(0.22 + signals * 0.11 + punctuation * 0.05 + length_factor * 0.32, 1.0)

    def _build_tasks(self, query: str, intent: str, complexity: float) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = [
            {
                "id": "task_understand",
                "type": "query_analysis",
                "description": "明确问题目标、输出风格和回答边界。",
                "dependencies": [],
                "tools": [],
                "estimated_seconds": 1,
                "resources": {"model": "light"},
            }
        ]

        if intent == "math":
            tasks.append(
                {
                    "id": "task_calculate",
                    "type": "tool_use",
                    "description": "调用计算工具，得到确定性结果。",
                    "dependencies": ["task_understand"],
                    "tools": ["calculator"],
                    "estimated_seconds": 1,
                    "resources": {"tool": "calculator"},
                }
            )
        elif intent == "weather":
            tasks.append(
                {
                    "id": "task_weather",
                    "type": "tool_use",
                    "description": "调用实时天气工具，获取目标地点的当前天气与今日概览。",
                    "dependencies": ["task_understand"],
                    "tools": ["weather_lookup"],
                    "estimated_seconds": 2,
                    "resources": {"tool": "weather_lookup"},
                }
            )
        elif intent == "web_search":
            tasks.append(
                {
                    "id": "task_web_search",
                    "type": "tool_use",
                    "description": "调用联网搜索工具，获取最新网页信息并筛选可信结果。",
                    "dependencies": ["task_understand"],
                    "tools": ["web_search"],
                    "estimated_seconds": 3,
                    "resources": {"tool": "web_search"},
                }
            )
        elif intent == "capability":
            tasks.append(
                {
                    "id": "task_capability_retrieve",
                    "type": "retrieval",
                    "description": "检索系统能力、协议支持和集成特性。",
                    "dependencies": ["task_understand"],
                    "tools": ["knowledge_base_search"],
                    "estimated_seconds": 2,
                    "resources": {"protocols": ["mcp", "function_calling"]},
                }
            )
        else:
            tools = ["knowledge_base_search", "knowledge_graph_search"]
            if intent in {"fact", "analysis"} and any(token in query.lower() for token in ["最新", "最近", "当前"]):
                tools.append("web_search")
            tasks.append(
                {
                    "id": "task_retrieve",
                    "type": "retrieval",
                    "description": "从向量知识库、知识图谱和在线工具中检索相关证据。",
                    "dependencies": ["task_understand"],
                    "tools": tools,
                    "estimated_seconds": 2,
                    "resources": {"retrieval_mode": "hybrid"},
                }
            )

        if complexity >= self.complexity_threshold:
            tasks.append(
                {
                    "id": "task_reason",
                    "type": "reasoning",
                    "description": "整理证据、识别依赖关系并形成结构化结论。",
                    "dependencies": [tasks[-1]["id"]],
                    "tools": [],
                    "estimated_seconds": 2,
                    "resources": {"model": "heavy"},
                }
            )

        tasks.append(
            {
                "id": "task_generate",
                "type": "generation",
                "description": "生成最终回答，并保留来源、局限和后续建议。",
                "dependencies": [tasks[-1]["id"]],
                "tools": [],
                "estimated_seconds": 2,
                "resources": {"model": "heavy" if complexity >= self.complexity_threshold else "light"},
            }
        )

        return tasks[: self.max_tasks]

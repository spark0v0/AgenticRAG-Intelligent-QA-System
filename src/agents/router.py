from __future__ import annotations

import json
import re
import asyncio
from typing import Any, Dict, List, Optional

from models import build_model_client

from .base_agent import AgentInput, AgentOutput, BaseAgent


class Router(BaseAgent):
    VALID_DIALOG_TYPES = {"casual_chat", "task_oriented"}
    VALID_EXPLICIT_INTENTS = {"deep_reasoning", "fast_answer", "retrieval_only", "tool_math"}
    VALID_INTENTS = {"chat", "fact", "analysis", "code", "math", "weather", "web_search", "vision", "capability"}

    def __init__(self, config: Dict[str, Any], model_config: Optional[Dict[str, Any]] = None):
        super().__init__("Router", config)
        self.simple_threshold = config.get("simple_threshold", 0.35)
        self.complex_threshold = config.get("complex_threshold", 0.68)
        self.use_llm = bool(config.get("use_llm", True))
        self.fallback_to_rules = bool(config.get("fallback_to_rules", True))
        self.llm_max_tokens = int(config.get("llm_max_tokens", 400))
        self.llm_timeout_seconds = float(config.get("llm_timeout_seconds", 12))
        self.llm_max_history_turns = int(config.get("llm_max_history_turns", 3))
        self.default_model_config = model_config or {}

    async def process(self, input_data: AgentInput) -> AgentOutput:
        if not self.validate_input(input_data):
            raise ValueError("Invalid input data")

        context = input_data.context or {}
        thinking_mode = context.get("thinking_mode")

        query = input_data.query.strip()
        has_images = bool(context.get("images") or context.get("attachments"))
        classification = self._rule_based_classification(query, has_images)
        scope = context.get("search_scope", "auto")
        if context.get("knowledge_base_id"):
            scope = "all" if scope == "all" else "local"
        # Clear commands should not pay for an additional model round trip.
        clear_intent = classification["intent"] in {"math", "weather", "web_search", "capability", "code", "analysis"}
        greeting = bool(re.fullmatch(r"(?:你好|您好|谢谢|再见|hello|hi)[！!。\s]*", query, re.I))
        should_use_llm = (self.use_llm and not has_images and scope == "auto"
                          and thinking_mode not in ("quick", "retrieval", "deep")
                          and not clear_intent and not greeting and not classification.get("explicit_intent")
                          and classification["intent"] == "chat" and len(query) > 12)
        if should_use_llm:
            classification = await self._classify_with_llm(query, context, input_data.history, classification)

        dialog_type = classification["dialog_type"]
        complexity = classification["complexity"]
        explicit_intent = classification.get("explicit_intent")
        intent = "vision" if has_images else classification["intent"]
        if scope in {"local", "web", "all"} and (thinking_mode != "quick" or context.get("knowledge_base_id")) and (not has_images or context.get("knowledge_base_id")):
            intent = "web_search" if scope == "web" else "fact"
            route = self._force_route("deep" if thinking_mode == "deep" else "retrieval", intent)
            route["reasoning"] = "按用户选择的检索范围执行。"
        elif thinking_mode in ("quick", "retrieval", "deep"):
            route = self._force_route(thinking_mode, intent)
        else:
            route = self._pick_route(query, dialog_type, complexity, explicit_intent, intent)
        model_tier = "heavy" if complexity >= self.complex_threshold else "light"

        return AgentOutput(
            content=f"route={route['route']} agent={route['agent']} model_tier={model_tier}",
            metadata={
                "route": route["route"],
                "target_agent": route["agent"],
                "priority": route["priority"],
                "reasoning": route["reasoning"],
                "dialog_type": dialog_type,
                "complexity": round(complexity, 4),
                "explicit_intent": explicit_intent,
                "model_tier": model_tier,
                "intent": intent,
                "response_mode": route["response_mode"],
                "routing_source": classification.get("source", "rules"),
                "classification_reason": classification.get("reason"),
                "classification_confidence": classification.get("confidence"),
                "router_provider": classification.get("provider"),
                "router_model": classification.get("model_name"),
                "router_error": classification.get("error"),
                "search_scope": scope,
                "classification_model_called": should_use_llm,
                "model_tier_applied": False,
            },
            confidence=self._output_confidence(complexity, classification),
        )

    def _rule_based_classification(self, query: str, has_images: bool = False) -> Dict[str, Any]:
        dialog_type = self._identify_dialog_type(query)
        complexity = self._assess_complexity(query)
        explicit_intent = self._detect_explicit_intent(query)
        intent = "vision" if has_images else self._detect_intent(query, dialog_type)
        return {
            "dialog_type": dialog_type,
            "complexity": complexity,
            "explicit_intent": explicit_intent,
            "intent": intent,
            "source": "rules",
            "reason": "基于关键词、符号和长度特征的规则兜底分类。",
            "confidence": min(0.72 + complexity * 0.16, 0.9),
        }

    async def _classify_with_llm(
        self,
        query: str,
        context: Dict[str, Any],
        history: List[Dict[str, Any]],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        model_config = self._router_model_config(context)
        if not model_config:
            return self._classification_fallback(fallback, "router model config is empty")
        if str(model_config.get("provider") or "").lower() == "mock":
            return self._classification_fallback(fallback, "mock model does not provide semantic routing")

        client = build_model_client(model_config)
        system_prompt = (
            "你是 AgenticRAG 系统的路由智能体，只负责理解用户请求并输出严格 JSON。"
            "不要回答用户问题，不要输出 Markdown。"
            "可选 dialog_type: casual_chat, task_oriented。"
            "可选 intent: chat, fact, analysis, code, math, weather, web_search, vision, capability。"
            "可选 explicit_intent: deep_reasoning, fast_answer, retrieval_only, tool_math, null。"
            "complexity 是 0 到 1 的数字，越接近 1 表示越需要多步规划或复杂推理。"
        )
        user_prompt = (
            "请根据用户问题和最近对话历史进行路由分类，输出如下 JSON：\n"
            "{\n"
            '  "dialog_type": "casual_chat|task_oriented",\n'
            '  "intent": "chat|fact|analysis|code|math|weather|web_search|vision|capability",\n'
            '  "complexity": 0.0,\n'
            '  "explicit_intent": null,\n'
            '  "confidence": 0.0,\n'
            '  "reason": "不超过30个汉字的分类理由"\n'
            "}\n\n"
            f"最近对话历史：{self._format_history(history)}\n"
            f"用户问题：{query}"
        )
        try:
            response = await asyncio.wait_for(client.generate(system_prompt, user_prompt), self.llm_timeout_seconds)
        except (TimeoutError, ValueError):
            return self._classification_fallback(fallback, "路由分类超时或不可用")
        if response.error:
            return self._classification_fallback(fallback, response.error)

        try:
            payload = self._parse_json_object(response.content)
            normalized = self._normalize_llm_classification(payload, fallback)
        except Exception as exc:
            return self._classification_fallback(fallback, f"invalid llm router output: {exc}")

        normalized.update(
            {
                "source": "llm",
                "provider": response.provider,
                "model_name": response.model_name,
                "fallback_used": response.fallback_used,
            }
        )
        return normalized

    def _router_model_config(self, context: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(self.default_model_config or {})
        context_model = context.get("model_config")
        if isinstance(context_model, dict):
            merged.update(context_model)
        router_model = self.config.get("model")
        if isinstance(router_model, dict):
            merged.update(router_model)
        if not merged:
            return {}
        merged["temperature"] = self.config.get("llm_temperature", 0)
        merged["max_tokens"] = self.llm_max_tokens
        merged["timeout_seconds"] = self.llm_timeout_seconds
        return merged

    def _classification_fallback(self, fallback: Dict[str, Any], error: str) -> Dict[str, Any]:
        data = dict(fallback)
        data["source"] = "rules"
        data["error"] = error
        data["reason"] = f"LLM 路由失败，使用规则兜底：{fallback.get('reason')}"
        return data

    def _parse_json_object(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("no JSON object found")
        parsed = json.loads(text[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("JSON root is not an object")
        return parsed

    def _normalize_llm_classification(self, payload: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
        dialog_type = str(payload.get("dialog_type") or fallback["dialog_type"]).strip()
        if dialog_type not in self.VALID_DIALOG_TYPES:
            dialog_type = fallback["dialog_type"]

        intent = str(payload.get("intent") or fallback["intent"]).strip()
        if intent not in self.VALID_INTENTS:
            intent = fallback["intent"]

        explicit_intent = payload.get("explicit_intent")
        if explicit_intent in ("", "null", "none", None):
            explicit_intent = fallback.get("explicit_intent")
        else:
            explicit_intent = str(explicit_intent).strip()
            if explicit_intent not in self.VALID_EXPLICIT_INTENTS:
                explicit_intent = fallback.get("explicit_intent")

        complexity = self._clamp_float(payload.get("complexity"), fallback["complexity"])
        confidence = self._clamp_float(payload.get("confidence"), 0.82)
        reason = str(payload.get("reason") or "LLM 语义分类").strip()[:80]
        return {
            "dialog_type": dialog_type,
            "complexity": complexity,
            "explicit_intent": explicit_intent,
            "intent": intent,
            "reason": reason,
            "confidence": confidence,
        }

    def _format_history(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return "无"
        items = []
        for turn in history[-self.llm_max_history_turns :]:
            query = str(turn.get("query") or "").strip()
            route = str(turn.get("route") or "").strip()
            intent = str(turn.get("intent") or "").strip()
            if query:
                items.append(f"query={query[:80]}, route={route}, intent={intent}")
        return "；".join(items) if items else "无"

    def _clamp_float(self, value: Any, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float(default)
        return max(0.0, min(number, 1.0))

    def _output_confidence(self, complexity: float, classification: Dict[str, Any]) -> float:
        base = self._clamp_float(classification.get("confidence"), 0.74 + complexity * 0.18)
        if classification.get("source") == "llm":
            return min(max(base, 0.78), 0.98)
        return min(base, 0.92)

    def _identify_dialog_type(self, query: str) -> str:
        lowered = query.lower()
        if re.fullmatch(r"(?:你好|您好|hello|hi|在吗|聊聊|你是谁|谢谢)[！!？?。\s]*", lowered):
            return "casual_chat"
        return "task_oriented"

    def _assess_complexity(self, query: str) -> float:
        lowered = query.lower()
        score = 0.14 + min(len(query) / 160, 0.34)
        score += sum(
            0.1
            for token in ["分析", "比较", "区别", "设计", "实现", "why", "how", "plan", "reason", "步骤", "架构"]
            if token in lowered
        )
        if any(token in lowered for token in ["请详细", "深入", "完整", "系统性", "成品标准"]):
            score += 0.14
        if query.count("，") + query.count(",") + query.count("。") > 1:
            score += 0.08
        return min(score, 1.0)

    def _detect_explicit_intent(self, query: str) -> Optional[str]:
        lowered = query.lower()
        if any(token in lowered for token in ["深度思考", "详细分析", "deep thinking"]):
            return "deep_reasoning"
        if any(token in lowered for token in ["快速回答", "简短回答", "quick answer"]):
            return "fast_answer"
        if any(token in lowered for token in ["只用工具", "只查资料", "tool only", "检索一下"]):
            return "retrieval_only"
        if re.search(r"\d\s*[+*/-]\s*\d", query):
            return "tool_math"
        return None

    def _detect_intent(self, query: str, dialog_type: str) -> str:
        lowered = query.lower()
        if re.search(r"\d\s*[+*/-]\s*\d", query):
            return "math"
        if any(token in lowered for token in ["天气", "气温", "温度", "下雨", "weather", "forecast"]):
            return "weather"
        if any(token in lowered for token in ["最新", "搜索", "查一下", "帮我查", "新闻", "官网", "网页", "互联网", "web"]):
            return "web_search"
        if any(token in lowered for token in ["图片", "图像", "照片", "截图", "image", "photo", "screenshot"]):
            return "vision"
        if any(token in lowered for token in ["能力", "支持", "协议", "mcp", "langchain"]):
            return "capability"
        if any(token in lowered for token in ["代码", "code", "python", "bug", "函数"]):
            return "code"
        if any(token in lowered for token in ["分析", "比较", "区别", "方案", "设计", "架构"]):
            return "analysis"
        if dialog_type == "casual_chat":
            return "chat"
        if any(token in lowered for token in ["什么是", "定义", "介绍", "原理", "流程", "资料"]):
            return "fact"
        return "chat" if len(query) < 24 else "fact"

    def _pick_route(
        self,
        query: str,
        dialog_type: str,
        complexity: float,
        explicit_intent: Optional[str],
        intent: str,
    ) -> Dict[str, str]:
        lowered = query.lower()
        analysis_signals = sum(1 for token in ["分析", "比较", "区别", "架构", "方案", "设计"] if token in lowered)

        if explicit_intent == "fast_answer":
            return {"route": "direct", "agent": "generator", "priority": "low", "reasoning": "用户显式要求快速回答。", "response_mode": "chat"}
        if explicit_intent == "retrieval_only":
            return {"route": "retrieval", "agent": "retriever", "priority": "medium", "reasoning": "用户显式要求先检索。", "response_mode": "grounded"}
        if explicit_intent == "deep_reasoning":
            return {"route": "planning", "agent": "planner", "priority": "high", "reasoning": "用户显式要求深度分析。", "response_mode": "analysis"}
        if explicit_intent == "tool_math":
            return {"route": "retrieval", "agent": "retriever", "priority": "medium", "reasoning": "检测到算术表达式，优先走工具调用。", "response_mode": "math_tool"}

        if intent == "math":
            return {"route": "retrieval", "agent": "retriever", "priority": "medium", "reasoning": "识别为计算类问题，优先调用计算工具。", "response_mode": "math_tool"}
        if intent == "weather":
            return {"route": "retrieval", "agent": "retriever", "priority": "high", "reasoning": "识别为实时天气查询，需要调用在线天气工具。", "response_mode": "weather_tool"}
        if intent == "web_search":
            return {"route": "retrieval", "agent": "retriever", "priority": "high", "reasoning": "识别为实时或联网信息查询，优先走在线搜索工具。", "response_mode": "grounded"}
        if intent == "capability":
            return {"route": "retrieval", "agent": "retriever", "priority": "medium", "reasoning": "问题偏向系统能力说明，优先走检索与协议工具。", "response_mode": "grounded"}
        if intent == "vision":
            return {"route": "direct", "agent": "generator", "priority": "high", "reasoning": "识别到图片输入，进入多模态回答模式。", "response_mode": "vision"}

        if dialog_type == "casual_chat" or intent == "chat":
            return {"route": "direct", "agent": "generator", "priority": "low", "reasoning": "识别为日常对话，优先走自然聊天模式。", "response_mode": "chat"}

        if analysis_signals >= 2 or (intent == "analysis" and complexity >= 0.45):
            return {"route": "planning", "agent": "planner", "priority": "high", "reasoning": "问题带有明显分析与推理特征，进入规划模式。", "response_mode": "analysis"}

        if intent in {"fact", "code"}:
            if complexity >= self.complex_threshold:
                return {"route": "planning", "agent": "planner", "priority": "high", "reasoning": "问题同时具备检索和多步分析特征。", "response_mode": "analysis"}
            return {"route": "retrieval", "agent": "retriever", "priority": "medium", "reasoning": "问题需要检索支持证据。", "response_mode": "grounded"}

        if complexity < self.simple_threshold:
            return {"route": "direct", "agent": "generator", "priority": "low", "reasoning": "问题较简单，直接回答。", "response_mode": "chat"}
        if complexity < self.complex_threshold:
            return {"route": "retrieval", "agent": "retriever", "priority": "medium", "reasoning": "问题中等复杂度，先检索再生成。", "response_mode": "grounded"}
        return {"route": "planning", "agent": "planner", "priority": "high", "reasoning": "问题复杂度较高，进入规划模式。", "response_mode": "analysis"}

    def _force_route(self, thinking_mode: str, intent: str) -> Dict[str, str]:
        if thinking_mode == "quick":
            return {"route": "direct", "agent": "generator", "priority": "low", "reasoning": "用户选择快速回答模式。", "response_mode": "chat"}
        if thinking_mode == "retrieval":
            mode = "weather_tool" if intent == "weather" else "grounded"
            return {"route": "retrieval", "agent": "retriever", "priority": "medium", "reasoning": "用户选择知识检索模式。", "response_mode": mode}
        # deep
        return {"route": "planning", "agent": "planner", "priority": "high", "reasoning": "用户选择深度分析模式。", "response_mode": "analysis"}

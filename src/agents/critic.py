from __future__ import annotations

from typing import Any, Dict, List

from retrieval import tokenize

from .base_agent import AgentInput, AgentOutput, BaseAgent

RELAXED_MODES = {"chat", "math_tool", "weather_tool", "service_notice", "live_data_notice", "vision"}


class Critic(BaseAgent):
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Critic", config)
        self.quality_threshold = config.get("quality_threshold", 0.72)
        self.retrieval_retry_threshold = config.get("retrieval_retry_threshold", 0.55)

    async def process(self, input_data: AgentInput) -> AgentOutput:
        if not self.validate_input(input_data):
            raise ValueError("Invalid input data")

        context = input_data.context or {}
        answer = str(context.get("content", ""))
        documents = context.get("documents", [])
        mode = str(context.get("mode") or "grounded")
        score_breakdown = self._evaluate(answer, input_data.query, documents, mode)
        overall_score = round(sum(score_breakdown.values()) / len(score_breakdown), 4)
        need_revision = overall_score < self.quality_threshold and mode not in RELAXED_MODES
        need_retrieval_retry = bool(documents) and score_breakdown["evidence_support"] < self.retrieval_retry_threshold and mode not in RELAXED_MODES
        feedback = self._build_feedback(score_breakdown, need_revision, need_retrieval_retry, documents, mode)
        suggestions = self._build_suggestions(score_breakdown, documents, mode)

        return AgentOutput(
            content=f"Critic score={overall_score}",
            metadata={
                "score": overall_score,
                "feedback": feedback,
                "suggestions": suggestions,
                "need_revision": need_revision,
                "need_retrieval_retry": need_retrieval_retry,
                "criteria_scores": score_breakdown,
                "mode": mode,
            },
            confidence=overall_score,
        )

    def _evaluate(self, answer: str, query: str, documents: List[Dict[str, Any]], mode: str) -> Dict[str, float]:
        query_terms = set(tokenize(query))
        answer_terms = set(tokenize(answer))
        matched = len(query_terms.intersection(answer_terms))
        relevance = min(0.45 + matched * 0.08, 1.0)
        avg_doc_score = 0.0
        if documents:
            avg_doc_score = sum(float(doc.get("score", doc.get("similarity", 0.0))) for doc in documents[:4]) / min(len(documents), 4)

        if mode == "chat":
            evidence = 0.82 if not documents else min(0.72 + avg_doc_score * 0.25, 1.0)
            citation = 0.9 if not documents else 0.92
            completeness = min(0.58 + len(answer) / 900, 0.96)
            clarity = 0.9 if len(answer) >= 12 else 0.72
            grounding = 0.82 if not documents else min(0.62 + avg_doc_score * 0.35, 0.98)
        elif mode in {"math_tool", "weather_tool"}:
            evidence = 0.96 if documents else 0.84
            citation = 0.94 if documents else 0.82
            completeness = min(0.72 + len(answer) / 1200, 0.98)
            clarity = 0.92
            grounding = 0.95 if documents else 0.82
        elif mode in {"service_notice", "live_data_notice"}:
            evidence = 0.9
            citation = 0.9
            completeness = min(0.68 + len(answer) / 1200, 0.96)
            clarity = 0.9
            grounding = 0.9
        else:
            evidence = min(0.3 + len(documents) * 0.08 + avg_doc_score * 0.35, 1.0) if documents else 0.3
            citation = 0.92 if ("[S" in answer or "来源" in answer) and documents else 0.4
            completeness = min(0.4 + len(answer) / 700, 1.0)
            clarity = 0.88 if any(marker in answer for marker in ["1.", "2.", "3.", "4.", "- ", "\n"]) else 0.62
            grounding = 0.85 if documents and any(doc.get("source") in answer for doc in documents[:3]) else min(0.45 + avg_doc_score * 0.5, 1.0)

        return {
            "relevance": round(relevance, 4),
            "evidence_support": round(evidence, 4),
            "citation": round(citation, 4),
            "completeness": round(completeness, 4),
            "clarity": round(clarity, 4),
            "grounding": round(grounding, 4),
        }

    def _build_feedback(
        self,
        scores: Dict[str, float],
        need_revision: bool,
        need_retrieval_retry: bool,
        documents: List[Dict[str, Any]],
        mode: str,
    ) -> str:
        weakest = min(scores, key=scores.get)
        parts = [
            f"Overall quality {'requires revision' if need_revision else 'is acceptable'}.",
            f"Weakest dimension: {weakest}={scores[weakest]:.2f}.",
            f"Response mode: {mode}.",
        ]
        if not documents and mode not in RELAXED_MODES:
            parts.append("No supporting documents were retrieved; confidence is limited.")
        if need_retrieval_retry:
            parts.append("Evidence quality is weak and retrieval should be retried with a refined query.")
        return " ".join(parts)

    def _build_suggestions(self, scores: Dict[str, float], documents: List[Dict[str, Any]], mode: str) -> List[str]:
        if mode in RELAXED_MODES:
            return ["当前回答已符合该模式的基本要求，可按需做轻量润色。"]

        suggestions: List[str] = []
        if scores["evidence_support"] < 0.65:
            suggestions.append("补充更多高质量证据，必要时改写查询后重检索。")
        if scores["citation"] < 0.7:
            suggestions.append("增加显式来源标注，并保持引用编号和来源列表一致。")
        if scores["completeness"] < 0.72:
            suggestions.append("补全结论、依据、局限和后续建议四个部分。")
        if scores["grounding"] < 0.68 and documents:
            suggestions.append("回答中应更明确地绑定检索证据，减少脱离证据的泛化表述。")
        if not suggestions:
            suggestions.append("当前答案质量可接受，仅需少量润色。")
        return suggestions[:4]

from __future__ import annotations

import re
from typing import Any, Dict
from .base_agent import AgentInput, AgentOutput, BaseAgent

RELAXED_MODES = {"chat", "math_tool", "weather_tool", "service_notice", "live_data_notice", "vision"}


class Critic(BaseAgent):
    """Verifiable evidence checks, not a factual-accuracy or prose-length score."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("Critic", config)

    async def process(self, input_data: AgentInput) -> AgentOutput:
        context = input_data.context or {}
        answer = str(context.get("content", ""))
        sources = context.get("source_map", [])
        mode = context.get("mode", "grounded")
        body = answer.split("来源列表：", 1)[0]
        body = re.sub(r"```[\s\S]*?```|`[^`]*`", "", body)
        cited = set(re.findall(r"\[(S\d+)\]", body))
        available = {item["citation_id"] for item in sources}
        unknown = sorted(cited - available)
        grounded = mode not in RELAXED_MODES
        abstained = any(word in body for word in ["证据不足", "未检索到", "无法确认", "没有足够", "无法核实"])
        issues = []
        if unknown:
            issues.append("引用了不存在的来源编号：" + "、".join(unknown))
        if grounded and sources and not cited:
            issues.append("有检索证据，但正文没有关联来源编号")
        missing_evidence = grounded and not sources and not abstained
        if missing_evidence:
            issues.append("没有检索证据，回答需要明确证据不足及知识边界")
        checks = {"citation_ids_valid": not unknown,
                  "evidence_boundary_disclosed": not missing_evidence,
                  "body_citations_present": not (grounded and sources and not cited)}
        score = round(sum(checks.values()) / len(checks), 4)
        return AgentOutput(
            content="证据检查：" + ("；".join(issues) if issues else "未发现引用结构问题；事实仍需核实"),
            metadata={"score": score, "evaluation_kind": "evidence_checks_not_accuracy",
                      "checks": checks, "issues": issues, "unknown_citations": unknown,
                      "need_revision": bool(issues), "need_retrieval_retry": missing_evidence,
                      "feedback": "；".join(issues) or "引用结构检查通过，不代表事实核验通过。",
                      "suggestions": issues, "mode": mode},
            confidence=score,
        )

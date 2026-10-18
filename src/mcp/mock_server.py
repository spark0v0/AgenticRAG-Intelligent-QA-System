from __future__ import annotations

import re
from typing import Any, Dict, List
from pydantic import BaseModel


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,8}", re.UNICODE)


CAPABILITY_DOCS = [
    {
        "source": "mcp://capabilities/vector-retrieval",
        "content": "系统支持本地 Chroma 向量检索、词法检索和混合检索，并可根据查询复杂度自适应调整检索轮次。",
        "metadata": {"topic": "vector_retrieval", "protocol": "mcp"},
    },
    {
        "source": "mcp://capabilities/function-calling",
        "content": "系统支持将工具导出为 OpenAI 兼容的 function calling schema，并可由模型或规则选择工具。",
        "metadata": {"topic": "function_calling", "protocol": "mcp"},
    },
    {
        "source": "mcp://capabilities/langchain",
        "content": "系统以 LangChain Runnable 形式暴露统一入口，便于在链式编排中复用 Router、Planner、Retriever、Generator、Critic。",
        "metadata": {"topic": "langchain", "protocol": "mcp"},
    },
    {
        "source": "mcp://capabilities/trace-memory",
        "content": "系统支持会话短期记忆、执行轨迹记录、来源追踪与历史运行回看。",
        "metadata": {"topic": "trace_memory", "protocol": "mcp"},
    },
]


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name != "project_capability_lookup":
        raise ValueError(f"Unknown MCP tool: {name}")

    query = str(arguments.get("query", ""))
    limit = max(1, min(int(arguments.get("limit", 3)), 5))
    query_tokens = set(tokenize(query))

    ranked = []
    for doc in CAPABILITY_DOCS:
        doc_tokens = set(tokenize(doc["content"]))
        overlap = len(query_tokens.intersection(doc_tokens))
        score = 0.25 + overlap * 0.18
        if doc["metadata"]["topic"] in query.lower():
            score += 0.25
        ranked.append((score, doc))

    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [
        {
            "content": doc["content"],
            "source": doc["source"],
            "score": round(min(score, 1.0), 4),
            "metadata": doc["metadata"],
        }
        for score, doc in ranked[:limit]
    ]
    summary = "\n".join(f"- {item['content']}" for item in selected)
    return {
        "content": [{"type": "text", "text": summary}],
        "structuredContent": {"documents": selected},
        "isError": False,
    }


class CapabilityResult(BaseModel):
    documents: List[Dict[str, Any]]


def main() -> None:
    from mcp.server import MCPServer
    from mcp_types import ToolAnnotations
    server = MCPServer("agenticrag-capability-example")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True), structured_output=True)
    def project_capability_lookup(query: str, limit: int = 3) -> CapabilityResult:
        """查询项目预置能力说明（示例数据，不验证系统实际能力）。"""
        return CapabilityResult(**call_tool("project_capability_lookup", {"query": query, "limit": limit})["structuredContent"])

    server.run(transport="stdio")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


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
        "content": "系统支持会话短期记忆、执行轨迹记录、来源追踪和需求符合度审计，可用于中期检查展示。",
        "metadata": {"topic": "trace_memory", "protocol": "mcp"},
    },
]


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def make_response(message_id: int | None, result: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "result": result}
    if message_id is not None:
        payload["id"] = message_id
    return payload


def make_error(message_id: int | None, message: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "error": {"code": -32000, "message": message}}
    if message_id is not None:
        payload["id"] = message_id
    return payload


def write_message(payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header + body)
    sys.stdout.buffer.flush()


def read_message() -> Dict[str, Any] | None:
    headers: Dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        stripped = line.decode("utf-8").strip()
        if not stripped:
            break
        name, _, value = stripped.partition(":")
        headers[name.lower()] = value.strip()

    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    body = sys.stdin.buffer.read(content_length)
    return json.loads(body.decode("utf-8"))


def list_tools() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": "project_capability_lookup",
                "description": "检索 AgenticRAG 项目的能力说明、协议支持和系统特性。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "用户想了解的系统能力问题。"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": ["query"],
                },
            }
        ]
    }


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


def main() -> None:
    while True:
        message = read_message()
        if message is None:
            return
        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params") or {}

        try:
            if method == "initialize":
                write_message(
                    make_response(
                        message_id,
                        {
                            "protocolVersion": "2024-11-05",
                            "serverInfo": {"name": "agenticrag-mock-mcp-server", "version": "1.0.0"},
                            "capabilities": {"tools": {}},
                        },
                    )
                )
            elif method == "tools/list":
                write_message(make_response(message_id, list_tools()))
            elif method == "tools/call":
                result = call_tool(str(params.get("name", "")), params.get("arguments") or {})
                write_message(make_response(message_id, result))
            elif method == "notifications/initialized":
                continue
            else:
                write_message(make_error(message_id, f"Unsupported method: {method}"))
        except Exception as exc:
            write_message(make_error(message_id, str(exc)))


if __name__ == "__main__":
    main()

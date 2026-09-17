"""Isolated upstream fixtures. Imported only by tests, never by the application."""
import asyncio
import json
from pathlib import Path
import httpx
from openai import AsyncOpenAI

ANSWER = "## 夹具回答\n\n这是自动化测试专用内容，用于验证真实接口的流式传输、取消、历史恢复与来源关联。\n\n- Router 选择处理路径。\n- Retriever 返回检索证据。\n- Generator 生成回答，Critic 进行规则评审。\n\n```typescript\nconst status = 'success'\n```"


class FixtureStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        for i in range(0, len(ANSWER), 8):
            await asyncio.sleep(0.035)
            chunk = {"id": "fixture", "model": "fixture", "created": 0, "object": "chat.completion.chunk",
                     "choices": [{"index": 0, "delta": {"content": ANSWER[i:i + 8]}, "finish_reason": None}]}
            yield f"data: {json.dumps(chunk)}\n\n".encode()
        yield b'data: {"id":"fixture","model":"fixture","created":0,"object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'


def fixture_client(**kwargs):
    def handle(request):
        if json.loads(request.content).get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=FixtureStream())
        return httpx.Response(200, json={"id": "fixture", "model": "fixture", "created": 0, "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}]})
    return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))


async def select_fixture_tools(self, query, schemas, *, max_tools=2):
    return self._select_tools_with_heuristics(query, schemas, max_tools=max_tools)


def fixture_config(directory: Path):
    return {
        "model": {"provider": "openai", "model_name": "fixture", "api_key": "test-only", "base_url": "http://fixture.invalid/v1"},
        "router": {"use_llm": False},
        "system": {"memory_path": str(directory / "history.sqlite3"), "max_retries": 0},
        "retrieval": {"knowledge_paths": [str(Path(__file__).resolve().parents[1] / "README.md")],
                      "persist_dir": str(directory / "chroma"), "collection_name": "smoke"},
    }

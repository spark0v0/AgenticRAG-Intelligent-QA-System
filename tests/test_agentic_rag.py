import asyncio
import sys
from pathlib import Path

from pydantic import BaseModel, Field
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.base_agent import AgentInput
from core.rag_system import AgenticRAGSystem
from integrations.dify_tools import build_dify_tools
from models import build_model_client
from models.client import ModelClient, ModelResponse
from tests.workbench_fixtures import ANSWER
from tools.base import ToolDocument, ToolResult, ToolSpec

TEST_DATA_ROOT = Path("data/test_memory")


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "TEST_DATA_ROOT", tmp_path)
    original_generate = ModelClient.generate

    async def generate_fixture(self, system_prompt, user_prompt, **kwargs):
        if self.provider != "mock":
            return await original_generate(self, system_prompt, user_prompt, **kwargs)
        images = kwargs.get("images") or []
        content = f"已经收到 {len(images)} 张图片。测试仅验证附件传递，不执行视觉识别。" if images else ANSWER
        return ModelResponse(content, "fixture", self.model_name, {})

    monkeypatch.setattr(ModelClient, "generate", generate_fixture)


def build_system() -> AgenticRAGSystem:
    return AgenticRAGSystem(
        {
            "model": {"provider": "mock", "model_name": "test-model"},
            "model_profiles": [
                {
                    "id": "mock_default",
                    "label": "Mock Default",
                    "provider": "mock",
                    "model_name": "test-model",
                    "supports_vision": True,
                },
                {
                    "id": "mock_alt",
                    "label": "Mock Alt",
                    "provider": "mock",
                    "model_name": "alt-model",
                    "supports_vision": True,
                },
            ],
            "retrieval": {
                "knowledge_paths": ["README.md", "src"],
                "max_results": 5,
                "persist_dir": str(TEST_DATA_ROOT / "chroma"),
                "collection_name": "test_agenticrag_kb",
            },
            "system": {
                "max_retries": 1,
                "enable_visualization": True,
                "memory_path": str(TEST_DATA_ROOT / "sessions.json"),
            },
            "router": {"simple_threshold": 0.35, "complex_threshold": 0.68, "use_llm": False},
            "planner": {"max_tasks": 8, "complexity_threshold": 0.55},
            "retriever": {"max_attempts": 2, "max_results": 5},
            "generator": {"enable_citation": True, "max_context_docs": 3},
            "critic": {"quality_threshold": 0.72},
        }
    )


def test_end_to_end_analysis_query():
    system = build_system()
    result = asyncio.run(system.query("请分析 AgenticRAG 的核心组成"))
    assert result["answer"]
    assert result["session_id"]
    assert "execution_trace" in result
    assert "messages" in result
    assert result["turn_count"] == 1
    assert result["routing"]["route"] in {"planning", "retrieval", "direct"}


def test_chat_query_returns_natural_answer_with_mock():
    system = build_system()
    result = asyncio.run(system.query("你好，你是谁？"))
    assert "未检索到足够证据" not in result["answer"]
    assert result["routing"]["route"] == "direct"
    assert result["response_mode"] in {"chat", "service_notice"}


def test_router_detects_weather_query_as_realtime_retrieval():
    system = build_system()
    routing = asyncio.run(system.router.process(AgentInput(query="今天西安天气怎么样")))
    assert routing.metadata["route"] == "retrieval"
    assert routing.metadata["intent"] == "weather"
    assert routing.metadata["response_mode"] == "weather_tool"


def test_router_can_use_llm_semantic_classification(monkeypatch):
    system = build_system()
    system.router.use_llm = True

    async def fake_classify(query, context, history, fallback):
        classified = dict(fallback)
        classified.update(
            {
                "source": "llm",
                "dialog_type": "task_oriented",
                "intent": "web_search",
                "complexity": 0.43,
                "explicit_intent": None,
                "confidence": 0.91,
                "reason": "语义判断为近期信息检索",
                "provider": "fake",
                "model_name": "fake-router",
            }
        )
        return classified

    monkeypatch.setattr(system.router, "_classify_with_llm", fake_classify)

    routing = asyncio.run(system.router.process(AgentInput(query="帮我了解一下近期大模型工具协议进展")))

    assert routing.metadata["routing_source"] == "llm"
    assert routing.metadata["intent"] == "web_search"
    assert routing.metadata["route"] == "retrieval"
    assert routing.metadata["router_model"] == "fake-router"


def test_calculator_accepts_natural_language_expression():
    system = build_system()
    result = asyncio.run(system.retriever.registry.invoke("calculator", {"expression": "1+1=几"}))
    assert result["status"] == "success"
    assert result["documents"][0]["content"].endswith("= 2")


def test_memory_persists_per_session():
    system = build_system()
    session_id = "session-1"
    asyncio.run(system.query("什么是 AgenticRAG", session_id=session_id))
    asyncio.run(system.query("它和传统 RAG 有什么区别", session_id=session_id))
    history = system.memory.get_history(session_id)
    assert len(history) == 2
    assert history[-1]["response_mode"] in {"grounded", "analysis", "service_notice", "chat"}
    assert history[-1]["intent"] in {"fact", "analysis", "code", "chat"}


def test_langchain_adapter_is_optional():
    system = build_system()
    assert hasattr(system, "langchain_runnable")


def test_session_listing_and_detail():
    system = build_system()
    session_id = "session-detail"
    asyncio.run(system.query("什么是 AgenticRAG", session_id=session_id))
    sessions = system.list_sessions()
    assert any(item["session_id"] == session_id for item in sessions)

    detail = system.get_session_detail(session_id)
    assert detail["session_id"] == session_id
    assert detail["turn_count"] == 1
    assert len(detail["messages"]) == 2


def test_dify_tools_expose_all_agents():
    system = build_system()
    tools = build_dify_tools(system)
    assert set(tools) == {
        "router_tool",
        "planner_tool",
        "retriever_tool",
        "generator_tool",
        "critic_tool",
        "agentic_rag_query",
    }


def test_capability_report_marks_protocol_and_realtime_support():
    system = build_system()
    items = {item["title"]: item for item in system.build_capability_report()}
    assert items["工具使用与扩展"]["status"] == "met"
    assert items["多源检索与动态决策"]["status"] == "met"
    assert items["LangChain 集成"]["status"] == "met"


def test_tool_list_exposes_realtime_tools_and_protocols():
    system = build_system()
    tools = {item["name"]: item for item in system.list_tools()}
    assert tools["project_capability_lookup"]["protocol"] == "mcp"
    assert tools["knowledge_base_search"]["protocol"] == "function_calling"
    assert tools["calculator"]["protocol"] == "function_calling"
    assert tools["weather_lookup"]["protocol"] == "function_calling"
    assert tools["web_search"]["protocol"] == "function_calling"


def test_status_exposes_model_profiles_without_api_keys():
    system = build_system()
    status = system.system_status()
    profiles = {item["id"]: item for item in status["model_profiles"]}

    assert status["default_model_profile"] == "mock_default"
    assert profiles["mock_alt"]["model_name"] == "alt-model"
    assert "api_key" not in profiles["mock_alt"]


def test_query_can_select_model_profile():
    system = build_system()
    result = asyncio.run(system.query("你好", context={"model_profile": "mock_alt"}, session_id="model-profile-session"))

    assert result["model_profile"] == "mock_alt"
    assert result["model"] == "alt-model"


def test_tool_registry_returns_structured_validation_errors():
    system = build_system()
    result = asyncio.run(system.retriever.registry.invoke("web_search", {"query": "AgenticRAG", "limit": 99}))
    assert result["status"] == "error"
    assert "input validation failed" in (result["error"] or "")


def test_tool_registry_preserves_timeout_status():
    system = build_system()

    class SlowToolInput(BaseModel):
        query: str = Field(...)

    async def slow_tool(payload: SlowToolInput) -> ToolResult:
        await asyncio.sleep(0.05)
        return ToolResult(
            documents=[ToolDocument(content=payload.query, source="slow_tool", score=1.0)],
        )

    system.retriever.registry.register(
        ToolSpec(
            name="slow_tool",
            description="Simulate a timeout.",
            handler=slow_tool,
            input_model=SlowToolInput,
            timeout_seconds=0.01,
        )
    )

    result = asyncio.run(system.retriever.registry.invoke("slow_tool", {"query": "timeout"}))
    assert result["status"] == "timeout"
    assert "timed out" in (result["error"] or "")


def test_weather_live_data_notice_provides_conservative_decision_advice():
    system = build_system()
    output = asyncio.run(
        system.generator.process(
            AgentInput(
                query="西安这种天气适合爬秦岭吗",
                context={
                    "response_mode": "live_data_notice",
                    "tool_calls": [{"tool": "weather_lookup", "status": "error", "error": "network blocked"}],
                },
                history=[],
            )
        )
    )
    assert "保守建议" in output.content
    assert "爬秦岭" in output.content
    assert "天气数据没有成功获取" in output.content


def test_image_query_uses_vision_mode_and_records_attachment():
    system = build_system()
    image = {
        "type": "image",
        "filename": "sample.png",
        "mime_type": "image/png",
        "size": 68,
        "data_url": (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        ),
    }

    result = asyncio.run(system.query("", context={"images": [image]}, session_id="image-session"))

    assert result["response_mode"] == "vision"
    assert result["image_count"] == 1
    assert "已经收到 1 张图片" in result["answer"]
    assert result["messages"][0]["attachments"][0]["filename"] == "sample.png"


def test_deepseek_image_request_fails_before_sending_image_url():
    client = build_model_client(
        {
            "provider": "deepseek",
            "model_name": "deepseek-v4-pro",
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com",
        }
    )
    image = {
        "filename": "sample.png",
        "mime_type": "image/png",
        "data_url": "data:image/png;base64,AAAA",
    }

    response = asyncio.run(client.generate("system", "user", images=[image]))

    assert response.error
    assert "不支持图片输入" in response.error
    assert "image_url" in response.error

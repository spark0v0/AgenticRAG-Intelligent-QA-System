from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from utils.execution import current_execution

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover
    AsyncOpenAI = None

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass
class ModelResponse:
    content: str
    provider: str
    model_name: str
    usage: Dict[str, Any]
    fallback_used: bool = False
    error: str | None = None


@dataclass
class ToolSelectionResult:
    tool_names: List[str]
    provider: str
    model_name: str
    used_function_calling: bool
    raw_response: Dict[str, Any]


class ModelClient:
    def __init__(self, config: Dict[str, Any]):
        self.provider = config.get("provider", "").lower()
        self.model_name = config.get("model_name", "")
        self.temperature = config.get("temperature", 0.3)
        self.max_tokens = config.get("max_tokens", 1200)
        self.timeout = config.get("timeout_seconds", 30)
        self.base_url = config.get("base_url") or self._default_base_url(self.provider)
        self.api_key = self._configured_api_key(config)
        self.supports_streaming = bool(config.get("supports_streaming", True))
        self.supports_vision = bool(config.get("supports_vision", self._default_supports_vision(self.provider, self.model_name)))

    @property
    def supports_function_calling(self) -> bool:
        return self.provider in {"openai", "deepseek"} and self.is_available

    @property
    def is_available(self) -> bool:
        if not self.model_name:
            return False
        if self.provider in {"openai", "deepseek"}:
            return bool(self.api_key and AsyncOpenAI)
        return self.provider in {"ollama", "xinference"}

    def _default_base_url(self, provider: str) -> str | None:
        defaults = {
            "deepseek": "https://api.deepseek.com",
            "ollama": "http://localhost:11434/api/generate",
            "xinference": "http://localhost:9997/v1/chat/completions",
        }
        return defaults.get(provider)

    def _default_supports_vision(self, provider: str, model_name: str) -> bool:
        if provider == "deepseek":
            return False
        if provider == "openai":
            lowered = model_name.lower()
            return any(token in lowered for token in ["gpt-4o", "gpt-4.1", "gpt-5", "vision", "omni"])
        if provider in {"ollama", "xinference"}:
            return False
        return False

    def _resolve_api_key(self, provider: str) -> Optional[str]:
        env_map = {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "ollama": "OLLAMA_API_KEY",
            "xinference": "XINFERENCE_API_KEY",
        }
        env_key = env_map.get(provider)
        return os.getenv(env_key) if env_key else None

    def _configured_api_key(self, config: Dict[str, Any]) -> Optional[str]:
        if "api_key" in config:
            return config["api_key"]
        api_key_env = config.get("api_key_env")
        if api_key_env and os.getenv(str(api_key_env)):
            return os.getenv(str(api_key_env))
        return self._resolve_api_key(self.provider)

    async def generate_stream(self, system_prompt: str, user_prompt: str, *, images=None) -> ModelResponse:
        """Real upstream deltas. No automatic resubmit after a partial response."""
        execution = current_execution.get()
        if execution is None:
            return await self.generate(system_prompt, user_prompt, images=images)
        if images and not self.supports_vision:
            raise ValueError("当前模型不支持图片输入，请移除附件或选择视觉模型。")
        if self.provider not in {"openai", "deepseek"} or not self.supports_streaming:
            execution.emit("transport", {"mode": "buffered", "message": "此模型采用完整结果模式，仍会显示执行进度。"})
            return await self.generate(system_prompt, user_prompt, images=images)
        if not self.api_key or AsyncOpenAI is None:
            raise ValueError("模型尚未配置凭据，请配置后端环境变量后重启服务。")
        execution.emit("transport", {"mode": "stream", "message": "正在接收模型增量响应"})
        content: list[str] = []
        finished = False
        kwargs = {"api_key": self.api_key, "max_retries": 0, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        try:
            async with AsyncOpenAI(**kwargs) as client:
                stream = await client.chat.completions.create(
                    model=self.model_name, stream=True, temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "system", "content": system_prompt},
                              {"role": "user", "content": self._build_multimodal_content(user_prompt, images or [])}],
                )
                async with stream:
                    async for chunk in stream:
                        if not chunk.choices:
                            continue
                        choice = chunk.choices[0]
                        text = choice.delta.content or ""
                        if text:
                            content.append(text)
                            execution.delta(text)
                        if choice.finish_reason:
                            finished = True
                            if choice.finish_reason != "stop":
                                execution.emit("notice", {"message": f"模型结束原因：{choice.finish_reason}，请检查回答完整性。"})
            if not finished:
                raise ValueError("模型连接提前结束，未收到完成标记。已保留草稿，请手动重试。")
            if not content:
                raise ValueError("模型没有返回可展示的回答。")
        except asyncio.CancelledError:
            raise
        except ValueError:
            raise
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            suffix = f"，HTTP {status}" if status else ""
            raise ValueError(f"模型流式请求失败（{type(exc).__name__}{suffix}），请检查服务配置或网络后手动重试。") from exc
        return ModelResponse("".join(content), self.provider, self.model_name, {})

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
    ) -> ModelResponse:
        image_payload = images or []
        if image_payload and not self.supports_vision:
            reason = (
                "DeepSeek Chat Completions 当前按文本消息解析，不能接收 OpenAI Vision 的 image_url 内容。"
                if self.provider == "deepseek"
                else "当前提供方没有声明视觉输入能力，不能接收 image_url 内容。"
            )
            return self._error_response(
                f"当前模型配置 provider={self.provider}, model={self.model_name} 不支持图片输入；{reason}",
                model_name=self.model_name,
                fallback_used=False,
            )

        if self.provider in {"openai", "deepseek"}:
            if self.is_available:
                return await self._generate_openai_compatible(system_prompt, user_prompt, images=image_payload, stop=stop)
            return self._error_response(
                "模型客户端未就绪，请检查 API Key、Base URL 或网络连通性。",
                fallback_used=False,
            )
        if self.provider == "ollama":
            return await self._generate_ollama(system_prompt, user_prompt, images=images)
        if self.provider == "xinference":
            return await self._generate_xinference(system_prompt, user_prompt, images=images)
        return self._error_response("模型提供方未接入，请检查后端模型档案。", fallback_used=False)

    async def select_tools(
        self,
        query: str,
        tool_schemas: List[Dict[str, Any]],
        *,
        max_tools: int = 2,
    ) -> ToolSelectionResult:
        if self.supports_function_calling and tool_schemas:
            result = await self._select_tools_with_model(query, tool_schemas, max_tools=max_tools)
            if result.tool_names:
                return result
        return self._select_tools_with_heuristics(query, tool_schemas, max_tools=max_tools)

    async def _generate_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: Optional[List[Dict[str, Any]]] = None,
        stop: Optional[List[str]] = None,
    ) -> ModelResponse:
        kwargs = {"api_key": self.api_key, "max_retries": 0, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        try:
            async with AsyncOpenAI(**kwargs) as client:
                response = await client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": self._build_multimodal_content(user_prompt, images or [])},
                    ],
                    temperature=self.temperature, max_tokens=self.max_tokens, stop=stop,
                )
            content = response.choices[0].message.content or ""
            return ModelResponse(
                content=content.strip(),
                provider=self.provider,
                model_name=self.model_name,
                usage={
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                    "completion_tokens": getattr(response.usage, "completion_tokens", None),
                },
            )
        except Exception as exc:
            return ModelResponse(
                content="",
                provider=self.provider,
                model_name=self.model_name,
                usage={},
                error=f"模型请求失败（{type(exc).__name__}），请检查配置或网络后手动重试。",
            )

    async def _select_tools_with_model(
        self, query: str, tool_schemas: List[Dict[str, Any]], *, max_tools: int,
    ) -> ToolSelectionResult:
        kwargs = {"api_key": self.api_key, "timeout": self.timeout, "max_retries": 0}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        try:
            async with AsyncOpenAI(**kwargs) as client:
                response = await client.chat.completions.create(
                    model=self.model_name, temperature=0, max_tokens=256,
                    messages=[
                        {"role": "system", "content": (
                            "你是工具调度器。只选择最适合问题的工具。数学运算用 calculator；"
                            "实时天气用 weather_lookup；最新网页信息用 web_search；"
                            "项目能力用 project_capability_lookup；本地证据用 knowledge_base_search。"
                        )},
                        {"role": "user", "content": query},
                    ],
                    tools=tool_schemas, tool_choice="auto",
                )
            calls = response.choices[0].message.tool_calls or []
            names = list(dict.fromkeys(call.function.name for call in calls if getattr(call, "function", None)))
            return ToolSelectionResult(names[:max_tools], self.provider, self.model_name, True, {"tool_calls": names})
        except Exception:
            # The existing rule selector remains an explicit routing fallback, not an answer.
            return ToolSelectionResult([], self.provider, self.model_name, False, {"tool_calls": []})

    def _select_tools_with_heuristics(
        self,
        query: str,
        tool_schemas: List[Dict[str, Any]],
        *,
        max_tools: int,
    ) -> ToolSelectionResult:
        lowered = query.lower()
        available = [schema.get("function", {}).get("name") for schema in tool_schemas]
        selected: List[str] = []

        def add(name: str) -> None:
            if name in available and name not in selected:
                selected.append(name)

        if any(symbol in query for symbol in ["+", "-", "*", "/"]):
            add("calculator")
            return ToolSelectionResult(
                tool_names=selected[:1],
                provider="heuristic",
                model_name="heuristic-selector",
                used_function_calling=False,
                raw_response={"tool_calls": selected[:1]},
            )

        if any(token in lowered for token in ["天气", "气温", "温度", "下雨", "weather", "forecast"]):
            add("weather_lookup")
            return ToolSelectionResult(
                tool_names=selected[:1],
                provider="heuristic",
                model_name="heuristic-selector",
                used_function_calling=False,
                raw_response={"tool_calls": selected[:1]},
            )

        if any(token in lowered for token in ["最新", "搜索", "查一下", "帮我查", "新闻", "官网", "网页", "web", "互联网"]):
            add("web_search")
            return ToolSelectionResult(
                tool_names=selected[:1],
                provider="heuristic",
                model_name="heuristic-selector",
                used_function_calling=False,
                raw_response={"tool_calls": selected[:1]},
            )

        if any(token in lowered for token in ["mcp", "协议", "能力", "支持", "langchain", "function"]):
            add("project_capability_lookup")
            return ToolSelectionResult(
                tool_names=selected[:1],
                provider="heuristic",
                model_name="heuristic-selector",
                used_function_calling=False,
                raw_response={"tool_calls": selected[:1]},
            )
        if any(token in lowered for token in ["关系", "组成", "依赖", "链路", "架构"]):
            add("knowledge_graph_search")
            add("knowledge_base_search")
        else:
            add("knowledge_base_search")
            if any(token in lowered for token in ["分析", "比较", "区别"]):
                add("knowledge_graph_search")

        return ToolSelectionResult(
            tool_names=selected[:max_tools],
            provider="heuristic",
            model_name="heuristic-selector",
            used_function_calling=False,
            raw_response={"tool_calls": selected[:max_tools]},
        )

    async def _generate_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> ModelResponse:
        payload = {
            "model": self.model_name,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        image_payloads = self._ollama_image_payloads(images or [])
        if image_payloads:
            payload["images"] = image_payloads
        base_url = self.base_url or "http://localhost:11434/api/generate"
        return await asyncio.to_thread(self._post_json, base_url, payload)

    async def _generate_xinference(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> ModelResponse:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._build_multimodal_content(user_prompt, images or [])},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        base_url = self.base_url or "http://localhost:9997/v1/chat/completions"
        return await asyncio.to_thread(self._post_json, base_url, payload)

    def _post_json(self, url: str, payload: Dict[str, Any]) -> ModelResponse:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            content = data.get("response") or data.get("choices", [{}])[0].get("message", {}).get("content") or ""
            return ModelResponse(
                content=content.strip(),
                provider=self.provider,
                model_name=self.model_name,
                usage=data.get("usage", {}),
            )
        except Exception as exc:
            return self._error_response(f"模型请求失败（{type(exc).__name__}），请检查网络与后端配置。", model_name=self.model_name)

    def _error_response(
        self,
        error: str,
        *,
        model_name: str | None = None,
        fallback_used: bool = False,
    ) -> ModelResponse:
        return ModelResponse(
            content="",
            provider=self.provider,
            model_name=model_name or self.model_name,
            usage={},
            fallback_used=fallback_used,
            error=error,
        )

    def _build_multimodal_content(self, text: str, images: List[Dict[str, Any]]) -> str | List[Dict[str, Any]]:
        image_parts = []
        for image in images:
            data_url = str(image.get("data_url") or image.get("url") or "").strip()
            if not data_url:
                continue
            image_parts.append({"type": "image_url", "image_url": {"url": data_url}})

        if not image_parts:
            return text
        return [{"type": "text", "text": text}, *image_parts]

    def _ollama_image_payloads(self, images: List[Dict[str, Any]]) -> List[str]:
        payloads: List[str] = []
        for image in images:
            data_url = str(image.get("data_url") or "").strip()
            if not data_url:
                continue
            if "," in data_url and data_url.startswith("data:image/"):
                payloads.append(data_url.split(",", 1)[1])
            else:
                payloads.append(data_url)
        return payloads


def build_model_client(config: Dict[str, Any]) -> ModelClient:
    return ModelClient(config)

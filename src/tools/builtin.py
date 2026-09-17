from __future__ import annotations

import asyncio
import html
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import requests
from pydantic import BaseModel, Field

from retrieval import HybridKnowledgeBase, is_code_like, tokenize
from .base import ToolDocument, ToolResult, ToolSpec
from .mcp_client import StdioMCPClient

WEATHER_CODE_MAP = {
    0: "晴朗",
    1: "基本晴朗",
    2: "局部多云",
    3: "阴天",
    45: "有雾",
    48: "冻雾",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "浓毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    95: "雷暴",
}

TIME_WORDS = ["今天", "明天", "后天", "现在", "当前", "最近", "实时"]


class KnowledgeBaseSearchInput(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)
    include_code: bool = False
    prefer_documents: bool = True
    retrieval_mode: str = "hybrid"


class KnowledgeGraphSearchInput(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=10)


class CalculatorInput(BaseModel):
    expression: str


class CapabilityLookupInput(BaseModel):
    query: str
    limit: int = Field(default=3, ge=1, le=5)


class WeatherLookupInput(BaseModel):
    query: str | None = None
    location: str | None = None
    days: int = Field(default=1, ge=1, le=3)


class WebSearchInput(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=8)


def _normalize_expression(raw: str) -> str:
    text = (raw or "").strip().lower()
    replacements = {
        "×": "*",
        "x": "*",
        "÷": "/",
        "（": "(",
        "）": ")",
        "【": "(",
        "】": ")",
        "＝": "=",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    for marker in [
        "请问",
        "帮我算一下",
        "帮我算",
        "算一下",
        "算一算",
        "计算一下",
        "计算",
        "结果是",
        "等于多少",
        "等于几",
        "等于",
        "是多少",
        "多少",
        "几",
        "吗",
    ]:
        text = text.replace(marker, "")

    text = text.replace("?", "").replace("？", "")
    text = text.replace("=", "")
    text = re.sub(r"\s+", "", text)
    matches = [segment for segment in re.findall(r"[\d\.\+\-\*\/\(\)]+", text) if any(ch.isdigit() for ch in segment)]
    if not matches:
        return ""

    expression = max(matches, key=len).strip("+*/")
    while expression.endswith(("+", "-", "*", "/", ".")):
        expression = expression[:-1]
    return expression


def _extract_location(query: str) -> str:
    text = (query or "").strip()
    patterns = [
        r"(?:今天|明天|后天|现在|当前|最近)?([A-Za-z\u4e00-\u9fff·\-\s]{2,24}?)(?:的)?天气",
        r"(?:帮我查|查一下|看看|告诉我|查询)([A-Za-z\u4e00-\u9fff·\-\s]{2,24}?)(?:今天|明天|后天|现在|当前)?(?:的)?天气",
    ]
    candidate = ""
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1)
            break

    candidate = candidate or text.replace("天气", "")
    for word in ["帮我查", "查一下", "看看", "告诉我", "查询", "一下", "的", "怎么样", "如何", *TIME_WORDS]:
        candidate = candidate.replace(word, "")
    candidate = candidate.strip(" ，。?？")
    return candidate or "北京"


def _weather_description(code: Any) -> str:
    try:
        return WEATHER_CODE_MAP.get(int(code), "天气状况未知")
    except Exception:
        return "天气状况未知"


def _http_headers() -> Dict[str, str]:
    return {
        "User-Agent": "AgenticRAG/3.1 (+https://example.local)",
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    }


def _weather_lookup_sync(location: str, days: int) -> ToolResult:
    geo_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "zh", "format": "json"},
        headers=_http_headers(),
        timeout=12,
    )
    geo_response.raise_for_status()
    geo_data = geo_response.json()
    results = geo_data.get("results") or []
    if not results:
        return ToolResult(status="error", error=f"未找到地点：{location}")

    item = results[0]
    forecast_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": days,
            "timezone": "auto",
        },
        headers=_http_headers(),
        timeout=12,
    )
    forecast_response.raise_for_status()
    forecast = forecast_response.json()

    current = forecast.get("current") or {}
    daily = forecast.get("daily") or {}
    description = _weather_description(current.get("weather_code"))
    today_max = (daily.get("temperature_2m_max") or [None])[0]
    today_min = (daily.get("temperature_2m_min") or [None])[0]
    precipitation = (daily.get("precipitation_probability_max") or [None])[0]
    resolved_name = item.get("name") or location
    if item.get("admin1"):
        resolved_name = f"{resolved_name}，{item['admin1']}"
    if item.get("country"):
        resolved_name = f"{resolved_name}，{item['country']}"

    content = (
        f"{resolved_name} 当前天气：{description}，气温 {current.get('temperature_2m', '-')}°C，"
        f"体感 {current.get('apparent_temperature', '-')}°C，湿度 {current.get('relative_humidity_2m', '-')}%，"
        f"风速 {current.get('wind_speed_10m', '-')} km/h。"
        f"今日最高 {today_max if today_max is not None else '-'}°C，最低 {today_min if today_min is not None else '-'}°C，"
        f"降水概率 {precipitation if precipitation is not None else '-'}%。"
    )

    return ToolResult(
        documents=[
            ToolDocument(
                content=content,
                source="weather_lookup",
                score=0.98,
                confidence=0.94,
                metadata={
                    "location": resolved_name,
                    "latitude": item.get("latitude"),
                    "longitude": item.get("longitude"),
                    "timezone": forecast.get("timezone"),
                    "current": current,
                    "daily": {
                        "temperature_2m_max": daily.get("temperature_2m_max"),
                        "temperature_2m_min": daily.get("temperature_2m_min"),
                        "precipitation_probability_max": daily.get("precipitation_probability_max"),
                        "weather_code": daily.get("weather_code"),
                    },
                },
            )
        ],
        metadata={"backend": "open-meteo", "service": "weather"},
    )


def _strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(clean).strip()


def _web_search_sync(query: str, limit: int) -> ToolResult:
    documents: List[ToolDocument] = []

    ddg_response = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": 1, "no_redirect": 1, "skip_disambig": 1},
        headers=_http_headers(),
        timeout=12,
    )
    ddg_response.raise_for_status()
    ddg_data = ddg_response.json()

    if ddg_data.get("AbstractText"):
        documents.append(
            ToolDocument(
                content=f"{ddg_data.get('Heading') or query}：{ddg_data.get('AbstractText')}",
                source=ddg_data.get("AbstractURL") or "duckduckgo",
                score=0.9,
                confidence=0.82,
                metadata={
                    "provider": "duckduckgo_instant",
                    "title": ddg_data.get("Heading") or query,
                    "url": ddg_data.get("AbstractURL"),
                },
            )
        )

    related_topics = ddg_data.get("RelatedTopics") or []
    for topic in related_topics:
        if len(documents) >= limit:
            break
        if isinstance(topic, dict) and topic.get("Text"):
            documents.append(
                ToolDocument(
                    content=str(topic.get("Text")),
                    source=topic.get("FirstURL") or "duckduckgo",
                    score=0.74,
                    confidence=0.72,
                    metadata={"provider": "duckduckgo_related", "url": topic.get("FirstURL")},
                )
            )
        for nested in topic.get("Topics") or []:
            if len(documents) >= limit:
                break
            if nested.get("Text"):
                documents.append(
                    ToolDocument(
                        content=str(nested.get("Text")),
                        source=nested.get("FirstURL") or "duckduckgo",
                        score=0.7,
                        confidence=0.69,
                        metadata={"provider": "duckduckgo_related", "url": nested.get("FirstURL")},
                    )
                )

    if len(documents) < limit:
        wiki_response = requests.get(
            "https://zh.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "utf8": 1,
                "format": "json",
            },
            headers=_http_headers(),
            timeout=12,
        )
        wiki_response.raise_for_status()
        wiki_hits = wiki_response.json().get("query", {}).get("search", [])
        for hit in wiki_hits:
            if len(documents) >= limit:
                break
            title = hit.get("title") or query
            snippet = _strip_html(hit.get("snippet", ""))
            documents.append(
                ToolDocument(
                    content=f"{title}：{snippet}",
                    source=f"https://zh.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    score=0.78,
                    confidence=0.74,
                    metadata={"provider": "wikipedia", "title": title},
                )
            )

    if not documents:
        return ToolResult(status="error", error=f"未检索到可用网页结果：{query}")

    return ToolResult(documents=documents[:limit], metadata={"backend": "internet_search", "service": "web"})


def build_builtin_tools(config: Dict[str, Any]) -> List[ToolSpec]:
    retrieval_cfg = config.get("retrieval", {})
    root = Path(__file__).resolve().parents[2]
    kb = HybridKnowledgeBase(
        root_dirs=retrieval_cfg.get("knowledge_paths", ["README.md", "docs", "src", "config"]),
        include_globs=retrieval_cfg.get("include_globs", ["*.md", "*.txt", "*.py", "*.yaml", "*.yml"]),
        chunk_size=retrieval_cfg.get("chunk_size", 900),
        chunk_overlap=retrieval_cfg.get("chunk_overlap", 120),
        persist_dir=retrieval_cfg.get("persist_dir", "data/chroma"),
        collection_name=retrieval_cfg.get("collection_name", "agenticrag_kb"),
        embedding_dimension=retrieval_cfg.get("embedding_dimension", 384),
        retrieval_mode=retrieval_cfg.get("retrieval_mode", "hybrid"),
        max_document_chars=retrieval_cfg.get("max_document_chars", 12000),
    )

    graph = defaultdict(list)
    for relation in retrieval_cfg.get("knowledge_graph", []):
        source = relation.get("source")
        target = relation.get("target")
        if source and target:
            graph[str(source).lower()].append(relation)

    async def knowledge_base_search(payload: KnowledgeBaseSearchInput) -> ToolResult:
        documents = await asyncio.to_thread(
            kb.search,
            payload.query,
            payload.limit,
            prefer_documents=payload.prefer_documents,
            include_code=payload.include_code,
            retrieval_mode=payload.retrieval_mode,
        )
        return ToolResult(
            documents=[ToolDocument.model_validate(doc) for doc in documents],
            metadata={
                "backend": "chroma_hybrid",
                "knowledge_base": kb.stats(),
                "retrieval_mode": payload.retrieval_mode,
            },
        )

    async def graph_search(payload: KnowledgeGraphSearchInput) -> ToolResult:
        hits: List[ToolDocument] = []
        seen = set()
        for node in tokenize(payload.query):
            for relation in graph.get(node, []):
                fingerprint = (relation.get("source"), relation.get("target"), relation.get("relation"))
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                hits.append(
                    ToolDocument(
                        content=f"{relation['source']} -[{relation.get('relation', 'related_to')}]-> {relation['target']}",
                        source="knowledge_graph",
                        score=float(relation.get("confidence", 0.8)),
                        confidence=float(relation.get("confidence", 0.8)),
                        metadata=relation,
                    )
                )
        hits.sort(key=lambda item: item.score, reverse=True)
        return ToolResult(documents=hits[: payload.limit], metadata={"backend": "graph_config"})

    async def calculator(payload: CalculatorInput) -> ToolResult:
        normalized = _normalize_expression(payload.expression)
        if not normalized:
            return ToolResult(status="error", error="无法从问题中解析出有效算式")
        if not re.fullmatch(r"[\d\s\+\-\*\/\(\)\.]+", normalized):
            return ToolResult(status="error", error="invalid expression")

        result = eval(normalized, {"__builtins__": {}}, {})
        return ToolResult(
            documents=[
                ToolDocument(
                    content=f"{normalized} = {result}",
                    source="calculator",
                    score=1.0,
                    confidence=1.0,
                    metadata={"expression": normalized, "result": result},
                )
            ],
            metadata={"backend": "python_eval"},
        )

    async def capability_lookup(payload: CapabilityLookupInput) -> ToolResult:
        client = StdioMCPClient(
            [sys.executable, str(root / "src" / "mcp" / "mock_server.py")],
            cwd=str(root),
        )
        try:
            response = await client.call_tool("project_capability_lookup", payload.model_dump())
        finally:
            await client.close()

        structured = response.get("structuredContent") or {}
        documents = structured.get("documents") or []
        return ToolResult(
            documents=[ToolDocument.model_validate(doc) for doc in documents],
            metadata={
                "backend": "mcp_stdio",
                "mcp_server": "agenticrag-mock-mcp-server",
                "mcp_tool": "project_capability_lookup",
            },
        )

    async def weather_lookup(payload: WeatherLookupInput) -> ToolResult:
        location = (payload.location or _extract_location(payload.query or "")).strip()
        try:
            return await asyncio.to_thread(_weather_lookup_sync, location, payload.days)
        except Exception as exc:
            return ToolResult(status="error", error=f"天气查询失败：{exc}")

    async def web_search(payload: WebSearchInput) -> ToolResult:
        try:
            return await asyncio.to_thread(_web_search_sync, payload.query, payload.limit)
        except Exception as exc:
            return ToolResult(status="error", error=f"联网搜索失败：{exc}")

    return [
        ToolSpec(
            name="knowledge_base_search",
            description="Search the local AgenticRAG knowledge base with hybrid vector and lexical retrieval.",
            handler=knowledge_base_search,
            input_model=KnowledgeBaseSearchInput,
            tags=["retrieval", "vector", "hybrid"],
            timeout_seconds=20.0,
            protocol="function_calling",
            metadata={"category": "knowledge"},
        ),
        ToolSpec(
            name="knowledge_graph_search",
            description="Lookup configured knowledge-graph relations that explain entities and their dependencies.",
            handler=graph_search,
            input_model=KnowledgeGraphSearchInput,
            tags=["retrieval", "graph"],
            timeout_seconds=8.0,
            protocol="native",
            metadata={"category": "knowledge"},
        ),
        ToolSpec(
            name="calculator",
            description="Evaluate a deterministic arithmetic expression.",
            handler=calculator,
            input_model=CalculatorInput,
            tags=["tool", "math"],
            timeout_seconds=3.0,
            protocol="function_calling",
            metadata={"category": "utility"},
        ),
        ToolSpec(
            name="weather_lookup",
            description="Fetch real-time weather information for a city using an online weather service.",
            handler=weather_lookup,
            input_model=WeatherLookupInput,
            tags=["tool", "weather", "realtime"],
            timeout_seconds=15.0,
            protocol="function_calling",
            metadata={"category": "realtime"},
        ),
        ToolSpec(
            name="web_search",
            description="Search the public web for up-to-date information and summaries.",
            handler=web_search,
            input_model=WebSearchInput,
            tags=["tool", "search", "realtime"],
            timeout_seconds=15.0,
            protocol="function_calling",
            metadata={"category": "realtime"},
        ),
        ToolSpec(
            name="project_capability_lookup",
            description="Query the MCP capability server for information about supported protocols and system features.",
            handler=capability_lookup,
            input_model=CapabilityLookupInput,
            tags=["retrieval", "mcp", "capability"],
            timeout_seconds=10.0,
            protocol="mcp",
            metadata={"category": "capability"},
        ),
    ]


__all__ = ["build_builtin_tools", "is_code_like", "tokenize"]

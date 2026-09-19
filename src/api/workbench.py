"""Vue workbench API: compatible JSON routes plus request-scoped SSE."""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field, field_validator

from core.rag_system import AgenticRAGSystem
from utils.config import Config
from utils.execution import public_data

ROOT = Path(__file__).resolve().parents[2]
router = APIRouter()
systems: dict[str, AgenticRAGSystem] = {}
Mode = Literal["live"]


def get_system(mode: Mode = "live") -> AgenticRAGSystem:
    if mode not in systems:
        config = Config(os.getenv("AGENTICRAG_CONFIG", str(ROOT / "config/config.yaml"))).config
        system = AgenticRAGSystem(config)
        from api.providers import apply_settings
        apply_settings(system)
        system.memory.recover_interrupted_runs()
        systems[mode] = system
    return systems[mode]


class ImageAttachment(BaseModel):
    type: Literal["image"] = "image"
    filename: str = Field(default="image", max_length=255)
    mime_type: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    size: int | None = Field(default=None, ge=0, le=4 * 1024 * 1024)
    data_url: str = Field(max_length=5_600_000)

    @field_validator("data_url")
    @classmethod
    def validate_image(cls, value: str, info) -> str:
        mime = info.data.get("mime_type")
        prefix = f"data:{mime};base64,"
        if not value.startswith(prefix):
            raise ValueError("图片格式与 MIME 类型不匹配")
        try:
            decoded = base64.b64decode(value[len(prefix):], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("无效的图片编码") from exc
        if not decoded or len(decoded) > 4 * 1024 * 1024:
            raise ValueError("图片不能为空且不得超过 4MB")
        return value


class QueryRequest(BaseModel):
    query: str = Field(default="", max_length=20000)
    context: dict[str, Any] | None = None
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    run_id: UUID | None = None
    model_profile: str | None = None
    images: list[ImageAttachment] = Field(default_factory=list, max_length=4)


def query_context(request: QueryRequest, system: AgenticRAGSystem) -> dict:
    if not request.query.strip() and not request.images:
        raise HTTPException(422, "请输入问题或添加图片")
    profile = request.model_profile or system.default_model_profile
    if profile not in system.model_profiles:
        raise HTTPException(422, "模型配置不存在，请刷新后重新选择")
    from models import build_model_client
    client = build_model_client(system.model_profiles[profile]["config"])
    if client.provider not in {"openai", "deepseek", "ollama", "xinference"}:
        raise HTTPException(422, "此模型提供方尚未接入，请选择已支持的模型档案")
    if not client.is_available:
        raise HTTPException(503, "模型尚未配置凭据，请在模型供应商页面添加配置")
    # Public requests may select server profiles, never inject provider credentials/configuration.
    allowed = {"thinking_mode", "location", "retrieval_mode", "strategy", "search_scope", "knowledge_base_id"}
    context = {k: v for k, v in (request.context or {}).items() if k in allowed}
    if context.get("search_scope", "auto") not in {"auto", "local", "web", "all"}:
        raise HTTPException(422, "不支持的检索范围")
    if context.get("thinking_mode") not in {None, "", "quick", "retrieval", "deep"}:
        raise HTTPException(422, "不支持的思考模式")
    kb_id = context.get("knowledge_base_id")
    if kb_id:
        if not isinstance(kb_id, str) or len(kb_id) > 64:
            raise HTTPException(422, "知识库标识无效")
        from knowledge.service import get_service
        try:
            get_service().library(kb_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        if context.get("search_scope") == "web" or context.get("thinking_mode") == "quick":
            raise HTTPException(422, "已选择知识库，请使用本地或组合检索，不能跳过知识库直接回答")
        context["search_scope"] = "all" if context.get("search_scope") == "all" else "local"
    context["model_profile"] = profile
    if request.images:
        if not client.supports_vision:
            raise HTTPException(422, "所选模型不支持图片，请切换视觉模型")
        context["images"] = [item.model_dump() for item in request.images]
    return context


@router.post("/query")
async def query(request: QueryRequest, mode: Mode = "live"):
    system = get_system(mode)
    context = query_context(request, system)
    try:
        return public_data(await system.query(request.query, context, request.session_id))
    except ValueError as exc:
        raise HTTPException(502, public_data(str(exc))) from exc
    except asyncio.CancelledError as exc:
        raise HTTPException(499, "本轮执行已取消") from exc
    except Exception as exc:
        raise HTTPException(500, "执行失败，请检查模型或工具配置") from exc


@router.post("/query/stream")
async def query_stream(request: QueryRequest, mode: Mode = "live"):
    system = get_system(mode)
    context = query_context(request, system)
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=2048)

    def deliver(event: dict) -> None:
        # Bounded queue: slow/disconnected clients cannot consume unlimited memory.
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            if event["type"] in {"completed", "error", "cancelled"}:
                queue.get_nowait()
                queue.put_nowait(event)
                return
            raise ValueError("客户端读取过慢，本轮已停止，请重新连接")

    try:
        execution, task = system.start_query(request.query, context, request.session_id,
                                            str(request.run_id) if request.run_id else None, deliver)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    # Ensure the task's finally block is entered before the HTTP response can be disconnected.
    await asyncio.sleep(0)

    async def events():
        try:
            while True:
                if task.done() and queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] in {"completed", "cancelled", "error"}:
                    break
        finally:
            if not task.done():
                system.cancel_run(execution.run_id)
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
    })


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, mode: Mode = "live"):
    system = get_system(mode)
    task = system._run_tasks.get(run_id)
    accepted = system.cancel_run(run_id)
    if accepted and task:
        await asyncio.gather(task, return_exceptions=True)
    return public_data({"run_id": run_id, "cancelled": accepted, "run": system.memory.get_run(run_id)})


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str, mode: Mode = "live"):
    return {"session_id": session_id, "cancelled": get_system(mode).cancel_session(session_id)}


@router.get("/status")
async def status(mode: Mode = "live"):
    return public_data(get_system(mode).system_status())


@router.get("/runs")
async def runs(request: Request, search: str = "", status: str = "", offset: int = 0, limit: int = 30):
    if request.url.path == "/runs" and "text/html" in request.headers.get("accept", ""):
        index = ROOT / "frontend/dist/index.html"
        if index.exists():
            return FileResponse(index)
    return public_data(get_system().memory.search_runs(search[:200], status, max(offset, 0), min(max(limit, 1), 100)))


@router.get("/runs/{run_id}")
async def run_detail(run_id: str):
    memory = get_system().memory
    run = memory.get_run(run_id)
    if run is None:
        raise HTTPException(404, "运行记录不存在")
    return public_data({**run, "events": memory.get_events(run["session_id"], run_id)})


@router.get("/tools")
async def tools(request: Request, mode: Mode = "live"):
    # /tools predates the SPA. Preserve JSON clients while supporting browser refresh.
    if request.url.path == "/tools" and "text/html" in request.headers.get("accept", ""):
        index = ROOT / "frontend/dist/index.html"
        if index.exists():
            return FileResponse(index)
    return {"items": public_data(get_system(mode).list_tools())}


@router.get("/sessions")
async def sessions(mode: Mode = "live"):
    return {"items": public_data(get_system(mode).list_sessions())}


@router.get("/sessions/{session_id}")
async def session(session_id: str, mode: Mode = "live"):
    return public_data(get_system(mode).get_session_detail(session_id))


@router.get("/visualization/{session_id}")
async def visualization(session_id: str, run_id: str | None = None, mode: Mode = "live"):
    return {"session_id": session_id, "trace": get_system(mode).memory.get_events(session_id, run_id)}


@router.get("/requirements-audit")
async def audit(mode: Mode = "live"):
    return {"items": get_system(mode).build_capability_report(),
            "notice": "原有能力自述，不能替代实际验证；Critic 为规则评分，知识图谱来自配置，MCP 为示例服务。"}

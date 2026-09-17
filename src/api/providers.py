"""Local-only provider management; connection checks never generate paid completions."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from memory.provider_store import ProviderStore
from utils.execution import public_data

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


def local_management(request: Request):
    if not request.client or request.client.host not in LOCAL_HOSTS | {"testclient"}:
        raise HTTPException(403, "供应商管理仅允许本机访问")
    if request.url.hostname not in LOCAL_HOSTS:
        raise HTTPException(403, "请使用 localhost 或 127.0.0.1 访问设置")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).hostname not in LOCAL_HOSTS:
        raise HTTPException(403, "拒绝跨站配置请求")
    if request.method != "GET" and request.headers.get("x-workbench-request") != "1":
        raise HTTPException(403, "缺少工作台请求标识")


router = APIRouter(prefix="/settings", dependencies=[Depends(local_management)])
_store: ProviderStore | None = None


def get_store():
    global _store
    if _store is None:
        path = os.getenv("AGENTICRAG_SETTINGS", "data/settings/providers.sqlite3")
        _store = ProviderStore(Path(path))
    return _store


class ModelSettings(BaseModel):
    model_name: str = Field(min_length=1, max_length=160, pattern=r"^\S+$")
    label: str = Field(min_length=1, max_length=80)
    supports_vision: bool = False
    supports_streaming: bool = True
    enabled: bool = True
    max_tokens: int = Field(default=4096, ge=64, le=65536)


class ProviderSettings(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    protocol: Literal["openai", "deepseek", "ollama", "xinference"]
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=4096)
    clear_key: bool = False
    timeout_seconds: int = Field(default=90, ge=5, le=600)
    models: list[ModelSettings] = Field(default_factory=list, max_length=100)

    @field_validator("base_url")
    @classmethod
    def endpoint(cls, value):
        url = urlsplit(value.strip())
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("地址必须是无凭据、查询参数的 HTTP(S) 服务地址")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("远程供应商必须使用 HTTPS，本机服务可使用 HTTP")
        return value.strip().rstrip("/")

    @model_validator(mode="after")
    def unique_models(self):
        names = [model.model_name for model in self.models]
        if len(names) != len(set(names)):
            raise ValueError("同一供应商中模型 ID 不可重复")
        if self.protocol in {"ollama", "xinference"}:
            for model in self.models:
                model.supports_streaming = False
        return self


def apply_settings(system):
    # Replacing dictionaries leaves active executions' configuration snapshots intact.
    if not hasattr(system, "_file_profiles"):
        system._file_profiles = system.model_profiles
        system._file_default = system.default_model_profile
    profiles = {**system._file_profiles, **get_store().profiles()}
    system._verified_models = {key: value for key, value in system._verified_models.items()
                               if key in profiles and profiles[key] == system.model_profiles.get(key)}
    system.model_profiles = profiles
    default = get_store().default()
    system.default_model_profile = default if default in profiles else system._file_default


def refresh_systems():
    from api.workbench import systems
    for system in systems.values():
        apply_settings(system)


@router.get("/providers")
async def list_providers():
    return public_data({"items": get_store().list(), "default_profile": get_store().default(),
                        "credential_storage": "windows-dpapi" if os.name == "nt" else "local-file-0600"})


@router.post("/providers")
async def add_provider(body: ProviderSettings):
    identity = get_store().save(body.model_dump())
    refresh_systems()
    return {"id": identity}


@router.put("/providers/{identity}")
async def update_provider(identity: str, body: ProviderSettings):
    if not any(item["id"] == identity for item in get_store().list()):
        raise HTTPException(404, "供应商不存在")
    get_store().save(body.model_dump(), identity)
    refresh_systems()
    return {"id": identity}


@router.delete("/providers/{identity}")
async def remove_provider(identity: str):
    get_store().remove(identity)
    refresh_systems()
    return {"removed": True}


class DefaultSettings(BaseModel):
    profile_id: str = Field(max_length=400)


@router.put("/default-model")
async def default_model(body: DefaultSettings):
    from api.workbench import get_system
    system = get_system()
    if body.profile_id not in system.model_profiles:
        raise HTTPException(422, "模型不存在或已停用")
    get_store().default(body.profile_id)
    refresh_systems()
    return {"profile_id": body.profile_id}


@router.post("/providers/{identity}/check")
async def check_provider(identity: str):
    provider = next((item for item in get_store().list(private=True) if item["id"] == identity), None)
    if provider is None:
        raise HTTPException(404, "供应商不存在")
    key = provider["api_key"]
    if provider["protocol"] in {"openai", "deepseek"} and not key:
        raise HTTPException(422, "请先保存 API Key")
    endpoint = provider["base_url"] + ("/api/tags" if provider["protocol"] == "ollama" else "/models")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    models = []
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            async with client.stream("GET", endpoint, headers=headers) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 2_000_000:
                        raise ValueError("响应过大")
                import json
                payload = json.loads(content)
        entries = payload.get("models", []) if provider["protocol"] == "ollama" else payload.get("data", [])
        if not isinstance(entries, list):
            raise ValueError("模型列表格式错误")
        models = list(dict.fromkeys(str(item.get("id") or item.get("name"))[:160]
                                  for item in entries if isinstance(item, dict) and (item.get("id") or item.get("name"))))[:200]
        ok, message = True, "模型列表接口连接成功；生成与图片能力仍以实际调用为准。"
    except httpx.HTTPStatusError as exc:
        ok, message = False, f"连接失败（HTTP {exc.response.status_code}），请检查地址、凭据或模型列表接口支持情况。"
    except Exception:
        ok, message = False, "无法读取模型列表，请检查网络与接口地址；可手动添加模型。"
    if not get_store().record_check(identity, ok, message, provider):
        return {"ok": False, "message": "检测期间配置已变化，请重新检测", "models": []}
    return public_data({"ok": ok, "message": message, "models": models})

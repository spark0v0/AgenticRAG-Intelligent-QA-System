from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from api.workbench import router, systems
from api.providers import router as provider_router


@asynccontextmanager
async def lifespan(app):
    yield
    tasks = [task for system in systems.values() for task in list(system._run_tasks.values())]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="AgenticRAG 智能问答工作台", version="4.0.0", lifespan=lifespan)
app.include_router(router)
app.include_router(router, prefix="/api", include_in_schema=False)
app.include_router(provider_router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic's default response echoes invalid input, which can include credentials.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()
    ]})
DIST = ROOT / "frontend/dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/legacy", response_class=HTMLResponse, include_in_schema=False)
async def legacy():
    return HTMLResponse((ROOT / "src/api/dashboard.html").read_text(encoding="utf-8"))


@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    return FileResponse(ROOT / "frontend/public/favicon.svg", media_type="image/svg+xml")


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str):
    # Only known client routes get the SPA; misspelled API routes remain 404.
    if path not in {"", "chat", "tools", "system", "providers", "runs"}:
        raise HTTPException(404, "Not found")
    if (DIST / "index.html").exists():
        return FileResponse(DIST / "index.html")
    return HTMLResponse("<h1>AgenticRAG</h1><p>请在 frontend 中运行 npm install 和 npm run dev，或 npm run build 后重启服务。</p><a href='/legacy'>打开原始界面</a>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))

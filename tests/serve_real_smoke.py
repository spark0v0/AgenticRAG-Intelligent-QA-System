"""Manual real-service verification; never launched by automated tests/CI."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utils.config import Config
from core.rag_system import AgenticRAGSystem
from api.main import app
from api.workbench import systems
import uvicorn

if __name__ == "__main__":
    config = copy.deepcopy(Config().config)
    isolated = ROOT / ".cache" / "real-service-smoke"
    config.setdefault("system", {})["memory_path"] = str(isolated / "sessions.sqlite3")
    config.setdefault("retrieval", {})["persist_dir"] = str(isolated / "chroma")
    # Only repository-owned documentation/code is exposed in public screenshots.
    config["retrieval"]["knowledge_paths"] = [str(ROOT / "README.md"), str(ROOT / "src")]
    systems["live"] = AgenticRAGSystem(config)
    systems["live"].memory.recover_interrupted_runs()
    uvicorn.run(app, host="127.0.0.1", port=8002)

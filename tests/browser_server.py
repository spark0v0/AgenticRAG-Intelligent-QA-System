"""Disposable API process for Playwright. No credentials or real histories are loaded."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from workbench_fixtures import fixture_config, fixture_client, select_fixture_tools
from models import client
from core.rag_system import AgenticRAGSystem
from api.main import app
from api.workbench import systems
from api import providers
from memory.provider_store import ProviderStore
import uvicorn

if __name__ == "__main__":
    client.AsyncOpenAI = fixture_client
    client.ModelClient.select_tools = select_fixture_tools
    with TemporaryDirectory(prefix="agenticrag-browser-") as directory:
        providers._store = ProviderStore(Path(directory) / "settings" / "providers.sqlite3")
        systems["live"] = AgenticRAGSystem(fixture_config(Path(directory)))
        uvicorn.run(app, host="127.0.0.1", port=8010)

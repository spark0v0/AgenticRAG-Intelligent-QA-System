"""Empty, temporary workspace for documentation screenshots; no user config is loaded."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import dotenv
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
# The application normally loads .env. This standalone capture process must not read it.
dotenv.load_dotenv = lambda *args, **kwargs: False

from api.main import app
from api.workbench import systems
from api import providers
from core.rag_system import AgenticRAGSystem
from memory.provider_store import ProviderStore
from knowledge import service as knowledge_service


if __name__ == '__main__':
    with TemporaryDirectory(prefix='agenticrag-screenshots-') as directory:
        temporary = Path(directory)
        corpus = temporary / 'empty-corpus'
        corpus.mkdir()
        providers._store = ProviderStore(temporary / 'providers.sqlite3')
        knowledge_service._service = knowledge_service.KnowledgeService(temporary / 'knowledge')
        systems['live'] = AgenticRAGSystem({
            'model': {'provider': 'openai', 'model_name': '', 'api_key': ''},
            'router': {'use_llm': False},
            'system': {'memory_path': str(temporary / 'sessions.sqlite3')},
            'retrieval': {'knowledge_paths': [str(corpus)], 'persist_dir': str(temporary / 'chroma')},
        })
        uvicorn.run(app, host='127.0.0.1', port=8005)

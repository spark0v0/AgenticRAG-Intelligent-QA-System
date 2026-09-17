import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.rag_system import AgenticRAGSystem
from utils.config import Config


async def run_smoke_test() -> None:
    config = Config(str(ROOT / "config" / "config.yaml")).config
    rag_system = AgenticRAGSystem(config)

    queries = [
        "你好",
        "什么是 AgenticRAG？",
        "请分析 AgenticRAG 与传统 RAG 的区别",
        "1 + 1 * 3",
    ]

    print("AgenticRAG system smoke test")
    print("=" * 50)
    for query in queries:
        result = await rag_system.query(query)
        print(f"Query: {query}")
        print(f"Answer: {result['answer'][:180]}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Reasoning: {result['reasoning']}")
        print(f"Sources: {result.get('sources', [])}")
        print("-" * 50)


def test_system() -> None:
    asyncio.run(run_smoke_test())


if __name__ == "__main__":
    asyncio.run(run_smoke_test())

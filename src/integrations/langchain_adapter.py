from __future__ import annotations

from typing import Any, Dict


def build_langchain_runnable(system: Any) -> Any:
    try:
        from langchain_core.runnables import RunnableLambda
    except Exception:
        return None

    async def _invoke(payload: Dict[str, Any]) -> Dict[str, Any]:
        return await system.query(
            payload.get("query", ""),
            context=payload.get("context"),
            session_id=payload.get("session_id"),
        )

    return RunnableLambda(_invoke)

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class SessionMemory:
    def __init__(self, storage_path: str | Path):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, List[Dict[str, Any]]] = self._load()

    def _load(self) -> Dict[str, List[Dict[str, Any]]]:
        if not self.storage_path.exists():
            return {}
        try:
            return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save(self) -> None:
        self.storage_path.write_text(
            json.dumps(self._sessions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        history = self._sessions.get(session_id, [])
        return history[-limit:]

    def get_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self._sessions.get(session_id, []))

    def list_sessions(self) -> List[Dict[str, Any]]:
        sessions: List[Dict[str, Any]] = []
        for session_id, turns in self._sessions.items():
            if not turns:
                continue
            last_turn = turns[-1]
            sessions.append(
                {
                    "session_id": session_id,
                    "turn_count": len(turns),
                    "updated_at": last_turn.get("timestamp"),
                    "preview": last_turn.get("query", "")[:80],
                }
            )
        sessions.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
        return sessions

    def append_turn(self, session_id: str, turn: Dict[str, Any], limit: int = 20) -> None:
        history = self._sessions.setdefault(session_id, [])
        history.append(turn)
        self._sessions[session_id] = history[-limit:]
        self._save()

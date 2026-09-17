from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


class Config:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            return yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        return self.get_default_config()

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "model": {
                "provider": "openai",
                "model_name": "",
                "temperature": 0.3,
                "max_tokens": 1200,
                "timeout_seconds": 30,
            },
            "retrieval": {
                "knowledge_paths": ["README.md", "docs", "src", "config"],
                "include_globs": ["*.md", "*.txt", "*.py", "*.yaml", "*.yml"],
                "max_results": 8,
            },
            "system": {
                "max_retries": 2,
                "enable_visualization": True,
                "memory_path": "data/memory/sessions.json",
            },
        }

    def get(self, key: str, default: Any = None) -> Any:
        current: Any = self.config
        for part in key.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

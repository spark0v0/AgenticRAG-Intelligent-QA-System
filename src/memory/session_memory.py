"""Compatibility import for the transactional SQLite store.

Existing JSON paths are imported once without modifying the source file.
Keep the old module path available, without maintaining a second storage implementation.
"""
from .sqlite_memory import SessionMemory

__all__ = ["SessionMemory"]

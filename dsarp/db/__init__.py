"""Persistent SQLite backend for local mode (stdlib sqlite3, no extra deps).

The pipeline stays file-first; the DB is an optional index over runs so the UI/CLI
can observe history across sessions. `Store` is the single entry point.
"""
from .database import Database  # noqa: F401
from .repositories import Store  # noqa: F401

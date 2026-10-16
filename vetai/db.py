"""Доступ к базе данных SQLite.

Единственное хранилище MVP (REQ-39). Соединения создаются через ``connect``,
инициализация схемы — через ``init_database``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vetai.config import SCHEMA_PATH, get_database_path


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Открыть соединение с базой, при необходимости создав каталог."""
    path = Path(db_path) if db_path is not None else get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database(db_path: str | Path | None = None) -> None:
    """Создать таблицы, если их нет. Операция идемпотентна."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect(db_path)
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()

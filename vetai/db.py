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


def _migrate_price_items_to_kopeks(conn: sqlite3.Connection) -> None:
    """Привести ``price_items.price`` к INTEGER (цена в копейках).

    Старая схема (этап 2) объявила цену как NUMERIC — риск потери точности из-за
    float. Если таблица уже существует с не-INTEGER типом, она пересоздаётся по
    актуальной ``schema.sql``, а существующие строки переносятся **без потери**
    с переводом рублей в копейки. Другие таблицы (включая ``briefs``) не
    затрагиваются, поэтому сохранённые брифы не изменяются.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'price_items'"
    ).fetchone()
    if table_exists is None:
        return

    price_column = next(
        (
            column
            for column in conn.execute("PRAGMA table_info(price_items)").fetchall()
            if column["name"] == "price"
        ),
        None,
    )
    if price_column is None:
        return

    if (price_column["type"] or "").upper().startswith("INTEGER"):
        return  # уже копейки — миграция не нужна

    conn.execute("ALTER TABLE price_items RENAME TO price_items_legacy")
    # executescript перечитывает schema.sql: остальные таблицы не меняются
    # (IF NOT EXISTS), а price_items создаётся заново с INTEGER-ценой.
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(
        """
        INSERT INTO price_items (id, name, price, is_active)
        SELECT id, name, CAST(ROUND(price * 100) AS INTEGER), is_active
        FROM price_items_legacy
        """
    )
    conn.execute("DROP TABLE price_items_legacy")


def init_database(db_path: str | Path | None = None) -> None:
    """Создать таблицы и выполнить безопасные миграции. Операция идемпотентна."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect(db_path)
    try:
        conn.executescript(schema)
        _migrate_price_items_to_kopeks(conn)
        conn.commit()
    finally:
        conn.close()

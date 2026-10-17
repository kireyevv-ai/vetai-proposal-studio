"""Тесты безопасной миграции цены в копейки (NUMERIC -> INTEGER).

Миграция не должна терять данные прайса и не должна трогать сохранённые брифы.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vetai.db import connect, init_database

# Схема этапа 2 (до миграции): цена — NUMERIC, брифы не менялись.
_LEGACY_SCHEMA = """
CREATE TABLE briefs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client      TEXT NOT NULL,
    task        TEXT NOT NULL,
    services    TEXT NOT NULL,
    deadlines   TEXT NOT NULL,
    budget      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE price_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    price      NUMERIC NOT NULL,
    is_active  INTEGER NOT NULL DEFAULT 1
);
"""


def _create_legacy_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_LEGACY_SCHEMA)
        conn.execute(
            "INSERT INTO briefs (client, task, services, deadlines, budget, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "ООО «Пример»",
                "Внедрить решение",
                '["Внедрение решения"]',
                "30 дней",
                "100 000 руб.",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.execute(
            "INSERT INTO price_items (name, price, is_active) VALUES (?, ?, ?)",
            ("Аудит", 1500, 1),
        )
        conn.execute(
            "INSERT INTO price_items (name, price, is_active) VALUES (?, ?, ?)",
            ("Сопровождение", 250.5, 0),
        )
        conn.commit()
    finally:
        conn.close()


def test_legacy_numeric_prices_migrated_to_kopeks(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    _create_legacy_db(path)

    init_database(path)

    conn = connect(path)
    try:
        declared = conn.execute("PRAGMA table_info(price_items)").fetchall()
        price_type = next(
            col["type"] for col in declared if col["name"] == "price"
        )
        rows = conn.execute(
            "SELECT id, name, price, is_active FROM price_items ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    assert price_type.upper().startswith("INTEGER")
    assert [(row["id"], row["name"], row["price"], row["is_active"]) for row in rows] == [
        (1, "Аудит", 150000, 1),
        (2, "Сопровождение", 25050, 0),
    ]


def test_migration_does_not_touch_existing_briefs(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    _create_legacy_db(path)

    init_database(path)

    conn = connect(path)
    try:
        row = conn.execute("SELECT * FROM briefs WHERE id = 1").fetchone()
        total = conn.execute("SELECT COUNT(*) AS n FROM briefs").fetchone()["n"]
    finally:
        conn.close()

    assert total == 1
    assert row["client"] == "ООО «Пример»"
    assert row["services"] == '["Внедрение решения"]'
    assert row["budget"] == "100 000 руб."


def test_migration_is_idempotent_no_double_conversion(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    _create_legacy_db(path)

    init_database(path)
    init_database(path)  # повторный запуск не должен умножить цену снова

    conn = connect(path)
    try:
        prices = [
            row["price"]
            for row in conn.execute(
                "SELECT price FROM price_items ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()

    assert prices == [150000, 25050]


def test_fresh_database_needs_no_migration(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"

    init_database(path)

    conn = connect(path)
    try:
        price_type = next(
            col["type"]
            for col in conn.execute("PRAGMA table_info(price_items)").fetchall()
            if col["name"] == "price"
        )
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM price_items"
        ).fetchone()["n"]
    finally:
        conn.close()

    assert price_type.upper().startswith("INTEGER")
    assert count == 0

"""Репозиторий брифов.

Сохранение и чтение брифов (REQ-01, REQ-36). Услуги хранятся как JSON-массив
названий, поэтому набор услуг брифа фиксируется без привязки к ценам.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from vetai.db import connect
from vetai.models import Brief, SavedBrief


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_saved_brief(row: sqlite3.Row) -> SavedBrief:
    return SavedBrief(
        id=row["id"],
        client=row["client"],
        task=row["task"],
        services=json.loads(row["services"] or "[]"),
        deadlines=row["deadlines"],
        budget=row["budget"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def save_brief(brief: Brief, db_path: str | Path | None = None) -> int:
    """Сохранить бриф и вернуть его идентификатор."""
    now = _now_iso()
    services_json = json.dumps(list(brief.services), ensure_ascii=False)
    conn = connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO briefs (client, task, services, deadlines, budget, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                brief.client.strip(),
                brief.task.strip(),
                services_json,
                brief.deadlines.strip(),
                brief.budget.strip(),
                now,
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def get_brief(brief_id: int, db_path: str | Path | None = None) -> SavedBrief | None:
    """Получить бриф по идентификатору."""
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT * FROM briefs WHERE id = ?", (brief_id,)).fetchone()
        return _row_to_saved_brief(row) if row else None
    finally:
        conn.close()


def get_latest_brief(db_path: str | Path | None = None) -> SavedBrief | None:
    """Получить последний сохранённый бриф (для восстановления после перезапуска)."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM briefs ORDER BY updated_at DESC, id DESC LIMIT 1"
        ).fetchone()
        return _row_to_saved_brief(row) if row else None
    finally:
        conn.close()


def list_briefs(db_path: str | Path | None = None) -> list[SavedBrief]:
    """Все брифы от новых к старым."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM briefs ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        return [_row_to_saved_brief(row) for row in rows]
    finally:
        conn.close()


def to_brief(saved: SavedBrief) -> Brief:
    """Преобразовать сохранённый бриф в модель ввода (для префилла формы)."""
    return Brief(
        client=saved.client,
        task=saved.task,
        services=list(saved.services),
        deadlines=saved.deadlines,
        budget=saved.budget,
    )

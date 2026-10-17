"""Репозиторий коммерческих предложений и их версий.

Каждое КП связано с одним брифом (REQ-24); текст хранится в
``proposal_versions`` с номером версии (REQ-25). Генерация создаёт версию
``generated``. Поле ``current_version`` в ``proposals`` указывает на актуальную
версию (REQ-24). Точная политика версионирования — открытый вопрос OQ-03;
на текущем этапе новая версия создаётся на каждую генерацию.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from vetai.db import connect
from vetai.models import DraftSection, ProposalDraft


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_generated_version(
    brief_id: int,
    body: str,
    commercial_snapshot: str,
    db_path: str | Path | None = None,
) -> tuple[int, int, int]:
    """Создать (или обновить) КП для брифа и добавить версию ``generated``.

    Returns:
        (proposal_id, version_id, version).
    """
    now = _now_iso()
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, current_version FROM proposals WHERE brief_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (brief_id,),
        ).fetchone()

        if row is None:
            cursor = conn.execute(
                """
                INSERT INTO proposals (brief_id, current_version, created_at, updated_at)
                VALUES (?, 0, ?, ?)
                """,
                (brief_id, now, now),
            )
            proposal_id = int(cursor.lastrowid)
            next_version = 1
        else:
            proposal_id = int(row["id"])
            next_version = int(row["current_version"]) + 1

        version_cursor = conn.execute(
            """
            INSERT INTO proposal_versions
                (proposal_id, version, status, body, commercial_snapshot, created_at)
            VALUES (?, ?, 'generated', ?, ?, ?)
            """,
            (proposal_id, next_version, body, commercial_snapshot, now),
        )
        version_id = int(version_cursor.lastrowid)

        conn.execute(
            "UPDATE proposals SET current_version = ?, updated_at = ? WHERE id = ?",
            (next_version, now, proposal_id),
        )
        conn.commit()
        return proposal_id, version_id, next_version
    finally:
        conn.close()


def _build_draft(row: sqlite3.Row) -> ProposalDraft:
    body = _parse_body(row["body"])
    snapshot = _parse_json_object(row["commercial_snapshot"])
    sections = [
        DraftSection(
            key=str(item.get("key", "")),
            title=str(item.get("title", "")),
            text=str(item.get("text", "")),
            source=str(item.get("source", "model")),
        )
        for item in body.get("sections", [])
        if isinstance(item, dict)
    ]
    return ProposalDraft(
        proposal_id=int(row["proposal_id"]),
        version_id=int(row["version_id"]),
        version=int(row["version"]),
        status=str(row["status"]),
        brief_id=int(row["brief_id"]),
        provider=str(body.get("provider", "")),
        sections=sections,
        commercial_snapshot=snapshot,
        warnings=list(body.get("warnings", [])),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _parse_body(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _parse_json_object(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_latest_draft(db_path: str | Path | None = None) -> ProposalDraft | None:
    """Последний сгенерированный черновик (актуальная версия свежего КП).

    Используется экраном «Черновик». ``None`` — если КП ещё нет.
    """
    conn = connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT pv.id AS version_id, pv.version, pv.status, pv.body,
                   pv.commercial_snapshot, pv.created_at,
                   p.id AS proposal_id, p.brief_id
            FROM proposals AS p
            JOIN proposal_versions AS pv
              ON pv.proposal_id = p.id AND pv.version = p.current_version
            ORDER BY p.updated_at DESC, p.id DESC
            LIMIT 1
            """
        ).fetchone()
        return _build_draft(row) if row else None
    finally:
        conn.close()


def list_versions(
    proposal_id: int, db_path: str | Path | None = None
) -> list[dict]:
    """Краткий список версий КП (для будущего экрана истории, REQ-22)."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, version, status, created_at FROM proposal_versions "
            "WHERE proposal_id = ? ORDER BY version",
            (proposal_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

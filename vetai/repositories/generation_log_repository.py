"""Репозиторий логов генерации (REQ-30..REQ-32).

В ``generation_logs`` сохраняются промпт и ответ для диагностики. Запись
выполняется **уже обезличенным** текстом: маскирование персональных данных и
секретов делает вызывающий код (``services/generation.py``) перед сохранением.
Ключи и токены сюда не попадают (REQ-32, REQ-34).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from vetai.db import connect


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Допустимые статусы синхронизированы со схемой (schema.sql).
def save_generation_log(
    provider: str,
    prompt: str,
    response: str,
    status: str,
    proposal_version_id: int | None = None,
    db_path: str | Path | None = None,
) -> int:
    """Сохранить запись лога и вернуть её идентификатор.

    ``prompt`` и ``response`` должны быть предварительно обезличены.
    """
    now = _now_iso()
    conn = connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO generation_logs
                (proposal_version_id, provider, prompt, response, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (proposal_version_id, provider, prompt or "", response or "", status, now),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_logs(db_path: str | Path | None = None) -> list[dict]:
    """Все записи логов от новых к старым (для диагностики/тестов)."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM generation_logs ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

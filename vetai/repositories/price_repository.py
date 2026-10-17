"""Репозиторий прайса услуг (REQ-26, REQ-28).

Цены хранятся в **копейках** (целое число), поэтому денежные значения не
проходят через float (REQ-10, REQ-12). Удаление позиции допустимо, только если
она не используется в сохранённых брифах; иначе — архивирование (``is_active``),
чтобы существующие брифы не теряли связь с данными.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vetai.db import connect
from vetai.models import PriceItem
from vetai.repositories import brief_repository

_MAX_NAME_LENGTH = 200


def _row_to_item(row: sqlite3.Row) -> PriceItem:
    return PriceItem(
        id=row["id"],
        name=row["name"],
        price_kopeks=int(row["price"]),
        is_active=bool(row["is_active"]),
    )


def _check_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("Введите название услуги.")
    if len(cleaned) > _MAX_NAME_LENGTH:
        raise ValueError(
            f"Название услуги слишком длинное (максимум {_MAX_NAME_LENGTH} символов)."
        )
    return cleaned


def _check_price(price_kopeks: int) -> int:
    if not isinstance(price_kopeks, int) or isinstance(price_kopeks, bool):
        raise ValueError("Цена должна быть целым числом в копейках.")
    if price_kopeks < 0:
        raise ValueError("Цена не может быть отрицательной.")
    return price_kopeks


def _ensure_name_unique(
    conn: sqlite3.Connection,
    name: str,
    exclude_id: int | None = None,
) -> None:
    """Запретить дубликаты среди активных позиций (услуга брифа = название).

    Сравнение регистронезависимо и выполняется в Python: встроенный ``lower()``
    SQLite не сворачивает кириллицу.
    """
    target = name.casefold()
    excluded = exclude_id if exclude_id is not None else -1
    rows = conn.execute(
        "SELECT id, name FROM price_items WHERE is_active = 1"
    ).fetchall()
    for row in rows:
        if row["id"] != excluded and row["name"].strip().casefold() == target:
            raise ValueError(f"Услуга «{name}» уже есть в прайсе.")


def list_price_items(
    db_path: str | Path | None = None, include_archived: bool = False
) -> list[PriceItem]:
    """Все позиции прайса в порядке добавления (архивные — по желанию)."""
    sql = "SELECT * FROM price_items"
    if not include_archived:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY id"
    conn = connect(db_path)
    try:
        return [_row_to_item(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def get_price_item(item_id: int, db_path: str | Path | None = None) -> PriceItem | None:
    """Позиция прайса по идентификатору."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM price_items WHERE id = ?", (item_id,)
        ).fetchone()
        return _row_to_item(row) if row else None
    finally:
        conn.close()


def get_active_by_name(
    name: str, db_path: str | Path | None = None
) -> PriceItem | None:
    """Активная позиция по названию — точка доверенных данных для подстановки цен.

    Используется будущим модулем генерации (REQ-10, REQ-12): цена берётся отсюда,
    а не из текста модели.
    """
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM price_items WHERE is_active = 1 AND name = ?",
            (name,),
        ).fetchone()
        return _row_to_item(row) if row else None
    finally:
        conn.close()


def add_price_item(
    name: str, price_kopeks: int, db_path: str | Path | None = None
) -> int:
    """Добавить услугу в прайс. Вернуть идентификатор."""
    name = _check_name(name)
    price_kopeks = _check_price(price_kopeks)
    conn = connect(db_path)
    try:
        _ensure_name_unique(conn, name)
        cursor = conn.execute(
            "INSERT INTO price_items (name, price, is_active) VALUES (?, ?, 1)",
            (name, price_kopeks),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def update_price_item(
    item_id: int,
    name: str,
    price_kopeks: int,
    db_path: str | Path | None = None,
) -> None:
    """Изменить название и/или цену позиции."""
    name = _check_name(name)
    price_kopeks = _check_price(price_kopeks)
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM price_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Позиция прайса не найдена.")
        _ensure_name_unique(conn, name, exclude_id=item_id)
        conn.execute(
            "UPDATE price_items SET name = ?, price = ? WHERE id = ?",
            (name, price_kopeks, item_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_archived(
    item_id: int, archived: bool, db_path: str | Path | None = None
) -> None:
    """Архивировать позицию или вернуть её в прайс.

    Архивная позиция не предлагается в новых брифах, но сохранённые брифы её
    название не теряют. Возврат в прайс блокируется при конфликте названий.
    """
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM price_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Позиция прайса не найдена.")
        if not archived:
            _ensure_name_unique(conn, row["name"], exclude_id=item_id)
        conn.execute(
            "UPDATE price_items SET is_active = ? WHERE id = ?",
            (0 if archived else 1, item_id),
        )
        conn.commit()
    finally:
        conn.close()


def is_referenced_in_briefs(
    name: str, db_path: str | Path | None = None
) -> bool:
    """Проверить, используется ли услуга в сохранённых брифах.

    Если да — удалять её небезопасно: существующие брифы показывают это
    название как выбранную услугу. Архивирование в этом случае безопаснее.
    """
    targets = {name.strip().casefold()}
    for brief in brief_repository.list_briefs(db_path=db_path):
        if any(service.strip().casefold() in targets for service in brief.services):
            return True
    return False


def delete_price_item(item_id: int, db_path: str | Path | None = None) -> None:
    """Удалить позицию, только если это безопасно для существующих брифов.

    Raises:
        ValueError: позиция не найдена или используется в брифах (нужен архив).
    """
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM price_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Позиция прайса не найдена.")
        if is_referenced_in_briefs(row["name"], db_path=db_path):
            raise ValueError(
                "Услуга используется в сохранённых брифах: удаление недоступно, "
                "используйте архивирование."
            )
        conn.execute("DELETE FROM price_items WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()

"""Репозиторий шаблона структуры КП (REQ-07, REQ-27, REQ-13).

В MVP используется **единственный активный шаблон** (несколько шаблонов — вне
границ MVP, см. `docs/REQUIREMENTS.md`, раздел 5). Структура хранится в JSON:
``{"sections": [{"key": ..., "title": ...}]}``.

``key`` — стабильный идентификатор раздела; принадлежность к обязательным
разделам определяется **кодом** (``MANDATORY_SECTION_KEYS``), а не данными из
базы, поэтому обязательный раздел нельзя «разотметить» правкой JSON.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vetai.db import connect
from vetai.models import (
    DEFAULT_TEMPLATE_SECTIONS,
    MANDATORY_SECTION_KEYS,
    Template,
    TemplateSection,
)
from vetai.validation import validate_template_structure

DEFAULT_TEMPLATE_NAME = "Основной шаблон КП"


def _load_sections(raw: str) -> list[TemplateSection]:
    """Разобрать JSON структуры. Обязательность выводится из ключа раздела."""
    try:
        data = json.loads(raw)
        items = data["sections"]
        sections = []
        for item in items:
            key = str(item["key"])
            sections.append(
                TemplateSection(
                    key=key,
                    title=str(item["title"]),
                    mandatory=key in MANDATORY_SECTION_KEYS,
                )
            )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Не удалось прочитать шаблон: повреждённые данные в базе. "
            "Сохраните шаблон заново, чтобы восстановить структуру."
        ) from exc
    return sections


def _dump_sections(sections: list[TemplateSection]) -> str:
    payload = {
        "sections": [
            {"key": section.key, "title": section.title.strip()}
            for section in sections
        ]
    }
    return json.dumps(payload, ensure_ascii=False)


def _normalize(sections: list[TemplateSection]) -> list[TemplateSection]:
    """Обязательность раздела всегда выводится из кода, не из входных данных."""
    return [
        TemplateSection(
            key=section.key,
            title=section.title.strip(),
            mandatory=section.key in MANDATORY_SECTION_KEYS,
        )
        for section in sections
    ]


def get_active_template(db_path: str | Path | None = None) -> Template | None:
    """Активный шаблон или None, если он ещё не создан."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM templates WHERE is_active = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return Template(
            id=row["id"],
            name=row["name"],
            sections=_load_sections(row["structure"]),
            is_active=True,
        )
    finally:
        conn.close()


def ensure_default_template(db_path: str | Path | None = None) -> Template:
    """Вернуть активный шаблон, создав шаблон по умолчанию при его отсутствии.

    Шаблон по умолчанию создаётся один раз и дальше редактируется руководителем;
    повторные вызовы ничего не перезаписывают.
    """
    template = get_active_template(db_path)
    if template is not None:
        return template

    sections = _normalize(list(DEFAULT_TEMPLATE_SECTIONS))
    conn = connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO templates (name, structure, is_active) VALUES (?, ?, 1)",
            (DEFAULT_TEMPLATE_NAME, _dump_sections(sections)),
        )
        conn.commit()
        return Template(
            id=int(cursor.lastrowid),
            name=DEFAULT_TEMPLATE_NAME,
            sections=sections,
            is_active=True,
        )
    finally:
        conn.close()


def save_sections(
    sections: list[TemplateSection], db_path: str | Path | None = None
) -> Template:
    """Проверить и сохранить структуру активного шаблона (создав при необходимости).

    Raises:
        ValueError: структура не прошла валидацию (обязательные разделы,
            пустые заголовки, дубликаты ключей).
    """
    errors = validate_template_structure(sections)
    if errors:
        raise ValueError(" ".join(errors))

    normalized = _normalize(sections)
    structure = _dump_sections(normalized)
    existing = get_active_template(db_path)

    conn = connect(db_path)
    try:
        if existing is None:
            cursor = conn.execute(
                "INSERT INTO templates (name, structure, is_active) VALUES (?, ?, 1)",
                (DEFAULT_TEMPLATE_NAME, structure),
            )
            template_id = int(cursor.lastrowid)
            name = DEFAULT_TEMPLATE_NAME
        else:
            conn.execute(
                "UPDATE templates SET structure = ? WHERE id = ?",
                (structure, existing.id),
            )
            template_id = existing.id
            name = existing.name
        conn.commit()
        return Template(
            id=template_id, name=name, sections=normalized, is_active=True
        )
    finally:
        conn.close()

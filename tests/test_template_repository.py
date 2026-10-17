"""Тесты шаблона КП: единый активный шаблон, обязательные разделы, сохранение.

REQ-07, REQ-13, REQ-27: структура редактируется, но обязательные разделы
сохраняются; обязательность определяется кодом, а не данными базы.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vetai.models import (
    DEFAULT_TEMPLATE_SECTIONS,
    MANDATORY_SECTION_KEYS,
    TemplateSection,
)
from vetai.repositories import template_repository
from vetai.validation import validate_template_structure


def _default_sections() -> list[TemplateSection]:
    return list(DEFAULT_TEMPLATE_SECTIONS)


def test_get_active_template_is_none_before_ensure(db_path: Path) -> None:
    assert template_repository.get_active_template(db_path=db_path) is None


def test_ensure_default_creates_template_once(db_path: Path) -> None:
    first = template_repository.ensure_default_template(db_path=db_path)
    second = template_repository.ensure_default_template(db_path=db_path)

    assert first.id == second.id
    assert first.sections == second.sections == _default_sections()

    from vetai.db import connect
    conn = connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM templates").fetchone()["n"]
    finally:
        conn.close()
    assert count == 1


def test_default_structure_passes_validation() -> None:
    assert validate_template_structure(_default_sections()) == []


def test_mandatory_keys_are_in_default_template() -> None:
    keys = {section.key for section in _default_sections()}
    assert MANDATORY_SECTION_KEYS <= keys


def test_save_and_reload_roundtrip(db_path: Path) -> None:
    template_repository.ensure_default_template(db_path=db_path)
    sections = [
        TemplateSection(key="task", title="Задача клиента", mandatory=True),
        TemplateSection(key="about", title="О компании"),
        TemplateSection(key="scope", title="Состав работ", mandatory=True),
        TemplateSection(key="deadlines", title="Сроки", mandatory=True),
        TemplateSection(key="pricing", title="Стоимость", mandatory=True),
        TemplateSection(key="custom_1", title="Порядок оплаты"),
    ]

    saved = template_repository.save_sections(sections, db_path=db_path)
    loaded = template_repository.get_active_template(db_path=db_path)

    assert loaded is not None
    assert loaded.id == saved.id
    assert [section.key for section in loaded.sections] == [
        section.key for section in sections
    ]
    assert loaded.sections[0].title == "Задача клиента"
    assert loaded.sections[-1].title == "Порядок оплаты"


def test_save_rejects_missing_mandatory_section(db_path: Path) -> None:
    sections = [s for s in _default_sections() if s.key != "pricing"]
    with pytest.raises(ValueError, match="Обязательные разделы"):
        template_repository.save_sections(sections, db_path=db_path)


def test_save_rejects_empty_title(db_path: Path) -> None:
    sections = _default_sections()
    sections[0] = TemplateSection(key="about", title="   ")
    with pytest.raises(ValueError, match="пустой заголовок"):
        template_repository.save_sections(sections, db_path=db_path)


def test_save_rejects_duplicate_keys(db_path: Path) -> None:
    sections = _default_sections()
    sections.append(sections[0])
    with pytest.raises(ValueError, match="уникальные"):
        template_repository.save_sections(sections, db_path=db_path)


def test_mandatory_flag_derived_from_code_not_data(db_path: Path) -> None:
    spoofed = [
        TemplateSection(key="pricing", title="Стоимость", mandatory=False),
        TemplateSection(key="task", title="Описание задачи", mandatory=True),
        TemplateSection(key="scope", title="Состав работ", mandatory=True),
        TemplateSection(key="deadlines", title="Сроки", mandatory=True),
    ]

    template_repository.save_sections(spoofed, db_path=db_path)
    loaded = template_repository.get_active_template(db_path=db_path)

    assert loaded is not None
    by_key = {section.key: section for section in loaded.sections}
    assert by_key["pricing"].mandatory is True


def test_save_creates_template_when_absent(db_path: Path) -> None:
    saved = template_repository.save_sections(_default_sections(), db_path=db_path)

    loaded = template_repository.get_active_template(db_path=db_path)
    assert loaded is not None
    assert loaded.id == saved.id


def test_multiple_saves_keep_single_active_row(db_path: Path) -> None:
    template_repository.ensure_default_template(db_path=db_path)
    template_repository.save_sections(_default_sections(), db_path=db_path)
    template_repository.save_sections(_default_sections(), db_path=db_path)

    from vetai.db import connect
    conn = connect(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM templates WHERE is_active = 1"
        ).fetchone()["n"]
    finally:
        conn.close()
    assert count == 1


def test_corrupted_structure_raises_helpful_error(db_path: Path) -> None:
    from vetai.db import connect

    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO templates (name, structure, is_active) VALUES (?, ?, 1)",
            ("Повреждённый", "{not json"),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="повреждённые данные"):
        template_repository.get_active_template(db_path=db_path)

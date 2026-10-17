"""Уточнение единицы срока в старых КП (Часть Б, обратная совместимость).

Ранее сохранённые версии КП могли содержать срок только числом (например «30»)
без единицы измерения. Единица измерения **не назначается автоматически** —
пользователь явно выбирает её в интерфейсе (рабочие дни / календарные дни /
недели / месяцы). После подтверждения создаётся **новая версия** КП с полным
сроком; старая версия не изменяется.

Коммерческий снимок (цены) копируется без изменений — меняется только поле
``deadlines``; проверка перед экспортом не обходится и не отключается.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from vetai.deadlines import format_deadline, parse_deadline
from vetai.models import SOURCE_CODE, SOURCE_MODEL, ProposalDraft
from vetai.repositories import proposal_repository
from vetai.services import commercial, text_checks

_AMBIGUOUS_MARK = "единица измерения не указана"
_DEADLINES_KEY = "deadlines"


def legacy_deadline(draft: ProposalDraft) -> tuple[int | None, str | None]:
    """Извлечь срок из сохранённой версии КП.

    Сначала — из доверенного коммерческого снимка; при его отсутствии — из
    текста раздела «Сроки» (без переинтерпретации неоднозначной пометки).

    Returns:
        ``(значение, единица)``; единица ``None`` — срок неоднозначен.
    """
    snapshot = draft.commercial_snapshot or {}
    text = str(snapshot.get("deadlines", "") or "").strip()
    if text:
        return parse_deadline(text)

    section = next(
        (s for s in draft.sections if s.key == _DEADLINES_KEY), None
    )
    section_text = (section.text if section else "") or ""
    if _AMBIGUOUS_MARK in section_text:
        match = re.search(r"\d+", section_text)
        return (int(match.group()) if match else None), None
    return parse_deadline(section_text)


def needs_unit(draft: ProposalDraft) -> bool:
    """Требует ли версия уточнения единицы срока (число есть, единицы нет)."""
    value, unit = legacy_deadline(draft)
    return value is not None and unit is None


def build_corrected_version_text(
    draft: ProposalDraft, unit_key: str, db_path: str | Path | None = None
) -> tuple[str, str]:
    """Собрать тело и снимок новой версии с уточнённой единицей срока.

    Цены из сохранённого коммерческого снимка не меняются; обновляется только
    срок. Разделы модели сохраняются как есть, коммерческие разделы
    перерисовываются из снимка.

    Raises:
        ValueError: в версии нет числового срока для уточнения.
    """
    raw = proposal_repository.get_version_raw(draft.version_id, db_path=db_path)
    body = _parse_json_object(raw["body"]) if raw else {}
    snapshot = _parse_json_object(raw["commercial_snapshot"]) if raw else {}

    value, _unit = legacy_deadline(draft)
    if value is None:
        raise ValueError("В версии КП нет числового срока для уточнения.")

    new_deadline_text = format_deadline(value, unit_key)
    snapshot["deadlines"] = new_deadline_text

    data = commercial.data_from_snapshot(snapshot)
    warnings = commercial.warnings_for(data) + _risky_warnings(body.get("sections", []))

    rendered_deadline = commercial.render_deadline_section(new_deadline_text)
    sections = []
    for item in body.get("sections", []):
        if not isinstance(item, dict):
            continue
        section = dict(item)
        if section.get("key") == _DEADLINES_KEY:
            section["text"] = rendered_deadline
            section["source"] = SOURCE_CODE
        sections.append(section)

    new_body = {
        "provider": body.get("provider", ""),
        "sections": sections,
        "warnings": warnings,
        "validation": {"issues": []},
    }
    return (
        json.dumps(new_body, ensure_ascii=False),
        json.dumps(snapshot, ensure_ascii=False),
    )


def create_corrected_version(
    draft: ProposalDraft, unit_key: str, db_path: str | Path | None = None
) -> tuple[int, int]:
    """Создать новую версию КП с уточнённой единицей срока.

    Returns:
        ``(version_id, version)`` новой версии; старая версия не изменяется.
    """
    body, snapshot = build_corrected_version_text(draft, unit_key, db_path=db_path)
    return proposal_repository.append_edited_version(
        draft.proposal_id, body, snapshot, db_path=db_path
    )


def _risky_warnings(sections: list) -> list[str]:
    warnings: list[str] = []
    for item in sections:
        if not isinstance(item, dict) or item.get("source") != SOURCE_MODEL:
            continue
        title = item.get("title", item.get("key", ""))
        for fragment in text_checks.find_risky_fragments(str(item.get("text", ""))):
            warnings.append(
                f"В разделе «{title}» возможна неподтверждённая формулировка: "
                f"«{fragment}». Проверьте вручную перед экспортом."
            )
    return warnings


def _parse_json_object(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}

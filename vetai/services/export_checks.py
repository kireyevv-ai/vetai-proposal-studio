"""Защитная проверка КП перед экспортом PDF.

Критические ошибки блокируют экспорт (пустые обязательные разделы, расхождение
цен/сроков с прайсом и брифом, отсутствие цен в прайсе). Предупреждения — не
блокируют, сигнализируют о возможных неподтверждённых формулировках и
незаполненных разделах.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vetai.models import (
    DEFAULT_TEMPLATE_SECTIONS,
    MANDATORY_SECTION_KEYS,
    SOURCE_CODE,
    SOURCE_PLACEHOLDER,
    ProposalDraft,
)
from vetai.services import commercial, text_checks

_SECTION_TITLES = {section.key: section.title for section in DEFAULT_TEMPLATE_SECTIONS}


@dataclass
class ExportCheck:
    critical: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def can_export(self) -> bool:
        return not self.critical


def _normalize(text: str) -> str:
    if not text:
        return ""
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def check_sections(sections: list, snapshot: dict) -> ExportCheck:
    """Проверить набор разделов по снимку коммерческих данных."""
    check = ExportCheck()
    by_key = {getattr(s, "key", ""): s for s in sections}

    # Критичное: обязательные разделы присутствуют и заполнены
    for key in MANDATORY_SECTION_KEYS:
        section = by_key.get(key)
        title = _SECTION_TITLES.get(key, key)
        if section is None:
            check.critical.append(f"Обязательный раздел «{title}» отсутствует.")
            continue
        if not getattr(section, "text", "").strip():
            check.critical.append(f"Обязательный раздел «{title}» не заполнен.")

    # Критичное: у части услуг нет цены — итог не рассчитан
    missing = [str(x) for x in (snapshot.get("missing", []) or [])] if snapshot else []
    if missing:
        check.critical.append(
            "Не указана стоимость одной или нескольких услуг: "
            + ", ".join(missing)
            + "."
        )

    # Критичное: коммерческие разделы совпадают с расчётом по прайсу и брифу
    expected = commercial.expected_sections(snapshot) if snapshot else {}
    for key, exp in expected.items():
        section = by_key.get(key)
        if section is None:
            continue
        if _normalize(getattr(section, "text", "")) != _normalize(exp):
            title = getattr(section, "title", key)
            check.critical.append(
                f"Раздел «{title}» изменён вручную — стоимость или сроки "
                "не совпадают с расчётом по прайсу и брифу."
            )

    # Предупреждения: незаполненные и рискованные формулировки
    for section in sections:
        source = getattr(section, "source", "")
        text = getattr(section, "text", "")
        title = getattr(section, "title", getattr(section, "key", ""))
        if source == SOURCE_PLACEHOLDER or not text.strip():
            if getattr(section, "key", "") not in MANDATORY_SECTION_KEYS:
                check.warnings.append(
                    f"Раздел «{title}» не заполнен — требует уточнения."
                )
            continue
        if source != SOURCE_CODE:
            for frag in text_checks.find_risky_fragments(text):
                check.warnings.append(
                    f"В разделе «{title}» возможна неподтверждённая формулировка: «{frag}». Проверьте вручную перед экспортом."
                )

    return check


def check_for_export(draft: ProposalDraft) -> ExportCheck:
    return check_sections(draft.sections, draft.commercial_snapshot)
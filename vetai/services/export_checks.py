"""Защитная проверка КП перед экспортом PDF (REQ-14, Задача 3).

Критические ошибки блокируют экспорт (пустые обязательные разделы, расхождение
цен/сроков с доверенными данными). Предупреждения — не блокируют, сигнализируют
о возможных неподтверждённых формулировках и незаполненных разделах.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vetai.models import (
    CODE_SECTION_KEYS,
    MANDATORY_SECTION_KEYS,
    SOURCE_CODE,
    SOURCE_PLACEHOLDER,
    ProposalDraft,
)
from vetai.services import commercial, text_checks


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
    """Проверить набор разделов по снимку доверенных данных."""
    check = ExportCheck()
    by_key = {getattr(s, "key", ""): s for s in sections}

    # Критичное: обязательные разделы присутствуют и заполнены
    for key in MANDATORY_SECTION_KEYS:
        section = by_key.get(key)
        if section is None:
            check.critical.append(f"Обязательный раздел отсутствует: {key}.")
            continue
        if not getattr(section, "text", "").strip():
            title = getattr(section, "title", key)
            check.critical.append(f"Обязательный раздел «{title}» не заполнен.")

    # Критичное: коммерческие разделы совпадают с доверенными данными
    expected = commercial.expected_sections(snapshot) if snapshot else {}
    for key, exp in expected.items():
        section = by_key.get(key)
        if section is None:
            continue
        if _normalize(getattr(section, "text", "")) != _normalize(exp):
            title = getattr(section, "title", key)
            check.critical.append(
                f"Раздел «{title}» не совпадает с доверенными данными (возможна подмена цен/сроков)."
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
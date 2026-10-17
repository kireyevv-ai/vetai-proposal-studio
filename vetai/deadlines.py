"""Сроки: значение + единица измерения (Часть Б задания этапа №4).

Поле ``briefs.deadlines`` остаётся свободным текстом (обратная совместимость,
без миграции БД). Новые записи формируются из **числа** и **единицы измерения**
из согласованного набора (рабочие дни, календарные дни, недели, месяцы) и
хранятся в каноническом виде, например «30 календарных дней».

Старые неоднозначные записи (например «30» или «30 дней») **не
переинтерпретируются**: единица измерения не присваивается автоматически, при
отображении добавляется пометка «требует уточнения».

Склонение единиц выполняется по правилам русского языка
(1 календарный день, 2 календарных дня, 5 календарных дней).
"""

from __future__ import annotations

import re

# Ключ единицы -> падежные формы для числа (1 / 2–4 / 5+).
_UNIT_FORMS: dict[str, tuple[str, str, str]] = {
    "work_days": ("рабочий день", "рабочих дня", "рабочих дней"),
    "calendar_days": ("календарный день", "календарных дня", "календарных дней"),
    "weeks": ("неделя", "недели", "недель"),
    "months": ("месяц", "месяца", "месяцев"),
}

# Человекочитаемые названия для выбора в интерфейсе.
UNIT_LABELS: dict[str, str] = {
    "work_days": "рабочие дни",
    "calendar_days": "календарные дни",
    "weeks": "недели",
    "months": "месяцы",
}

UNIT_LABEL_TO_KEY: dict[str, str] = {
    label: key for key, label in UNIT_LABELS.items()
}

_NUMBER_RE = re.compile(r"\d+")


def plural_index(value: int) -> int:
    """Индекс падежной формы для числа (0 — «1 день», 1 — «2 дня», 2 — «5 дней»)."""
    number = abs(int(value)) % 100
    if 11 <= number <= 14:
        return 2
    number %= 10
    if number == 1:
        return 0
    if 2 <= number <= 4:
        return 1
    return 2


def format_deadline(value: int, unit_key: str) -> str:
    """Каноническая формулировка срока: «30 календарных дней».

    Raises:
        KeyError: неизвестная единица измерения.
    """
    forms = _UNIT_FORMS[unit_key]
    return f"{int(value)} {forms[plural_index(value)]}"


def compose_deadline(value: int | None, unit_key: str | None) -> str:
    """Собрать строку сроков из значения и единицы.

    Если хотя бы одна часть не задана — возвращается пустая строка (сроки не
    считаются указанными; валидация брифа заблокирует генерацию, REQ-03).
    """
    if value is None or unit_key is None:
        return ""
    return format_deadline(int(value), unit_key)


def detect_unit(text: str) -> str | None:
    """Определить единицу измерения по тексту или вернуть None (неоднозначно)."""
    low = (text or "").lower()
    if "недел" in low:
        return "weeks"
    if "месяц" in low or re.search(r"мес\b", low):
        return "months"
    if "дн" in low or "день" in low:
        if "рабоч" in low:
            return "work_days"
        if "календар" in low:
            return "calendar_days"
        # «30 дней» — без уточнения рабоч./календар. не переинтерпретируем.
        return None
    return None


def parse_deadline(text: str) -> tuple[int | None, str | None]:
    """Разобрать срок в пару ``(значение, единица)``.

    Возвращает ``(None, None)``, если число не найдено. Если число есть, но
    единица неоднозначна — ``(значение, None)`` (единицу не присваиваем).
    """
    match = _NUMBER_RE.search(text or "")
    if match is None:
        return None, None
    value = int(match.group())
    return value, detect_unit(text)


def normalize_deadline(text: str) -> str:
    """Канонизировать срок, если единица распознана; иначе вернуть как есть.

    Неоднозначные значения **не** переписываются (обратная совместимость).
    """
    value, unit = parse_deadline(text)
    if value is not None and unit is not None:
        return format_deadline(value, unit)
    return (text or "").strip()

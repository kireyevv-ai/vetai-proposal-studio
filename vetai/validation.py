"""Валидация данных: бриф, цена прайса, структура шаблона.

Бриф: проверка обязательных полей (REQ-02, REQ-03, REQ-05). Пустое обязательное
поле блокирует генерацию. Возвращаются понятные пользователю сообщения.

Цена: значение вводится текстом и преобразуется в **копейки** (целое число).
Отрицательные и непредставимые числа отклоняются — деньги не считаются во
float (REQ-10, REQ-12, REQ-26).

Шаблон: обязательные разделы должны присутствовать, заголовки непустые
(REQ-07, REQ-13, REQ-27).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from vetai.models import (
    DEFAULT_TEMPLATE_SECTIONS,
    MANDATORY_SECTION_KEYS,
    Brief,
    TemplateSection,
)

# Человекочитаемые названия обязательных полей.
FIELD_LABELS: dict[str, str] = {
    "client": "название клиента",
    "task": "описание задачи",
    "services": "хотя бы одна услуга",
    "deadlines": "сроки",
    "budget": "бюджет",
}


def validate_brief(brief: Brief) -> list[str]:
    """Вернуть список сообщений об ошибках. Пустой список — бриф корректен."""
    errors: list[str] = []

    if not brief.client or not brief.client.strip():
        errors.append("Заполните название клиента.")
    if not brief.task or not brief.task.strip():
        errors.append("Заполните описание задачи.")
    if not brief.services:
        errors.append("Выберите хотя бы одну услугу.")
    if not brief.deadlines or not brief.deadlines.strip():
        errors.append("Укажите сроки.")
    if not brief.budget or not brief.budget.strip():
        errors.append("Укажите бюджет.")

    return errors


def missing_required_labels(brief: Brief) -> list[str]:
    """Названия незаполненных обязательных полей (для подсказки в UI)."""
    missing: list[str] = []
    if not brief.client or not brief.client.strip():
        missing.append(FIELD_LABELS["client"])
    if not brief.task or not brief.task.strip():
        missing.append(FIELD_LABELS["task"])
    if not brief.services:
        missing.append(FIELD_LABELS["services"])
    if not brief.deadlines or not brief.deadlines.strip():
        missing.append(FIELD_LABELS["deadlines"])
    if not brief.budget or not brief.budget.strip():
        missing.append(FIELD_LABELS["budget"])
    return missing


def is_brief_valid(brief: Brief) -> bool:
    """True, если бриф можно использовать для генерации."""
    return not validate_brief(brief)


# --- Цена прайса (копейки, без float) -------------------------------------

# Целая часть + необязательная дробная из 1–2 знаков (копейки).
_PRICE_PATTERN = re.compile(r"\d+(?:\.\d{1,2})?")
_NEGATIVE_PRICE_PATTERN = re.compile(r"-\d+(?:\.\d{1,2})?")


def parse_price_to_kopeks(raw: str) -> int:
    """Разобрать введённую цену и вернуть её в копейках.

    Допускаются форматы вида ``1500``, ``1500.50``, ``1 500,50 руб.``, ``₽``.
    Отклоняются: пустая строка, текст, отрицательные числа, более двух знаков
    после точки (точность копеек).

    Raises:
        ValueError: сообщение на русском — для показа пользователю.
    """
    cleaned = (raw or "").strip().replace("\u00a0", " ")
    for suffix in ("₽", "руб.", "руб", "р."):
        cleaned = cleaned.replace(suffix, "")
    cleaned = cleaned.replace(" ", "").replace(",", ".")

    if not cleaned:
        raise ValueError("Введите цену числом, например 1500 или 1500,50.")

    if _NEGATIVE_PRICE_PATTERN.fullmatch(cleaned):
        raise ValueError("Цена не может быть отрицательной.")
    if not _PRICE_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "Цена должна быть числом больше или равным нулю, "
            "не более двух знаков после запятой (копейки)."
        )

    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:  # защита от неожиданных входов
        raise ValueError("Цена должна быть числом.") from exc

    return int(value * 100)


def format_price(price_kopeks: int) -> str:
    """Отобразить цену из копеек человекочитаемо: ``1 500 руб.`` / ``1 500,50 руб.``."""
    rubles = price_kopeks // 100
    kopeks = price_kopeks % 100
    whole = f"{rubles:,}".replace(",", " ")
    if kopeks == 0:
        return f"{whole} руб."
    return f"{whole},{kopeks:02d} руб."


# --- Структура шаблона КП -------------------------------------------------


def validate_template_structure(sections: list[TemplateSection]) -> list[str]:
    """Проверить структуру шаблона. Пустой список ошибок — структура корректна."""
    errors: list[str] = []

    if not sections:
        errors.append("Шаблон должен содержать хотя бы один раздел.")
        return errors

    keys = [section.key for section in sections]
    if len(keys) != len(set(keys)):
        errors.append("Разделы шаблона должны иметь уникальные идентификаторы.")

    for index, section in enumerate(sections, start=1):
        if not section.title or not section.title.strip():
            errors.append(f"У раздела {index} пустой заголовок.")

    missing = MANDATORY_SECTION_KEYS.difference(keys)
    if missing:
        default_titles = {
            section.key: section.title
            for section in DEFAULT_TEMPLATE_SECTIONS
        }
        titles = ", ".join(default_titles[key] for key in sorted(missing))
        errors.append(
            "Обязательные разделы нельзя удалять или скрывать: " + titles + "."
        )

    return errors

"""Валидация брифа.

Проверка обязательных полей (REQ-02, REQ-03, REQ-05). Пустой обязательный
поле блокирует генерацию. Возвращаются понятные пользователю сообщения.
"""

from __future__ import annotations

from vetai.models import Brief

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

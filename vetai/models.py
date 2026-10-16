"""Типизированные модели данных.

Простые dataclass-модели для явной схемы данных и проверки типов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Brief:
    """Бриф, введённый менеджером (REQ-01).

    ``services`` — список выбранных названий услуг.
    """

    client: str = ""
    task: str = ""
    services: list[str] = field(default_factory=list)
    deadlines: str = ""
    budget: str = ""


@dataclass
class SavedBrief:
    """Сохранённый в базе бриф с идентификатором и датами."""

    id: int
    client: str
    task: str
    services: list[str]
    deadlines: str
    budget: str
    created_at: datetime
    updated_at: datetime

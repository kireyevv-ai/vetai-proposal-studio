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


@dataclass
class PriceItem:
    """Позиция прайса (REQ-26).

    ``price_kopeks`` — цена в копейках (целое число). Деньги никогда не хранятся
    как float, чтобы исключить ошибки округления (REQ-10, REQ-12).
    """

    id: int
    name: str
    price_kopeks: int
    is_active: bool = True


@dataclass(frozen=True)
class TemplateSection:
    """Раздел шаблона КП (REQ-07, REQ-27).

    ``key`` — стабильный идентификатор раздела (не редактируется);
    ``title`` — заголовок, который руководитель может менять;
    ``mandatory`` — обязательный раздел: не может быть удалён.
    """

    key: str
    title: str
    mandatory: bool = False


@dataclass
class Template:
    """Активный шаблон структуры КП (единственный в MVP)."""

    id: int
    name: str
    sections: list[TemplateSection]
    is_active: bool = True


# Шаблон по умолчанию: создаётся при первом открытии «Настроек».
# Обязательные разделы привязаны к данным брифа и коммерческим условиям —
# их нельзя удалять (REQ-13).
DEFAULT_TEMPLATE_SECTIONS: tuple[TemplateSection, ...] = (
    TemplateSection(key="about", title="О компании"),
    TemplateSection(key="task", title="Описание задачи", mandatory=True),
    TemplateSection(key="scope", title="Состав работ и услуги", mandatory=True),
    TemplateSection(key="deadlines", title="Сроки", mandatory=True),
    TemplateSection(key="pricing", title="Стоимость", mandatory=True),
    TemplateSection(key="terms", title="Прочие условия"),
)

MANDATORY_SECTION_KEYS: frozenset[str] = frozenset(
    section.key for section in DEFAULT_TEMPLATE_SECTIONS if section.mandatory
)

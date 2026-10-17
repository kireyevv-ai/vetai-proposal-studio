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

# Разделы, которые вправе заполнять только модель — и только по данным брифа
# (REQ-06, REQ-13). Всё остальное либо подставляется программой, либо помечается
# как «требует уточнения» (см. политику заземления в generation._assemble_sections).
MODEL_SECTION_KEYS: frozenset[str] = frozenset({"task", "scope"})

# Разделы, которые заполняет исключительно программа из доверенных данных:
# цены — из прайса, сроки — из брифа (REQ-10, REQ-11, REQ-12).
CODE_SECTION_KEYS: frozenset[str] = frozenset({"pricing", "deadlines"})


# Источники содержимого раздела черновика КП (REQ-10, REQ-12).
SOURCE_MODEL = "model"  # текст сгенерирован AI-провайдером из данных брифа
SOURCE_CODE = "code"  # раздел сформирован программно из доверенных данных
SOURCE_PLACEHOLDER = "placeholder"  # нет доверенных данных — «требует уточнения»


@dataclass(frozen=True)
class DraftSection:
    """Раздел сгенерированного черновика КП.

    ``source`` фиксирует происхождение текста: коммерческие разделы
    (``pricing``, ``deadlines``) всегда ``code`` — их заполняет программа
    из прайса и брифа, а не модель (REQ-10, REQ-11, REQ-12). Разделы без
    доверенных данных получают ``placeholder`` с пустым текстом и пометкой
    «требует уточнения» (Часть А, п. 6).
    """

    key: str
    title: str
    text: str
    source: str


@dataclass
class ProposalDraft:
    """Версия черновика КП, прочитанная из базы (для экрана «Черновик»)."""

    proposal_id: int
    version_id: int
    version: int
    status: str
    brief_id: int
    provider: str
    sections: list[DraftSection]
    commercial_snapshot: dict
    warnings: list[str]
    created_at: datetime

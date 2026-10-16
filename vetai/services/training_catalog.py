"""Временный учебный каталог услуг для формы брифа.

ВАЖНО: это НЕ прайс. Каталог отделён от таблицы ``price_items`` и не содержит
цен. Он нужен только для выбора услуг в брифе на учебном этапе (REQ-01).
Реальные услуги и цены появятся в прайсе на отдельном этапе (REQ-26..REQ-28).
"""

from __future__ import annotations

from dataclasses import dataclass

TRAINING_CATALOG_NOTE = (
    "Временный учебный каталог услуг. Это не прайс: цены не заданы и не "
    "показываются. Коммерческие условия появятся позже из доверенных данных."
)


@dataclass(frozen=True)
class TrainingService:
    code: str
    name: str


TRAINING_SERVICES: tuple[TrainingService, ...] = (
    TrainingService("audit", "Аудит текущих процессов (учебная)"),
    TrainingService("consulting", "Консультация по задаче (учебная)"),
    TrainingService("implementation", "Внедрение решения (учебная)"),
    TrainingService("support", "Сопровождение (учебная)"),
    TrainingService("training", "Обучение сотрудников (учебная)"),
)


def service_names() -> list[str]:
    """Названия услуг для виджета выбора (без цен)."""
    return [service.name for service in TRAINING_SERVICES]


def filter_known(names: list[str]) -> list[str]:
    """Оставить только названия из текущего каталога (защита от устаревших данных)."""
    known = set(service_names())
    return [name for name in names if name in known]

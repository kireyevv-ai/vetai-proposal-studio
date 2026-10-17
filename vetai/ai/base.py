"""Общий интерфейс AI-провайдера (REQ-08).

Слой генерации зависит только от этой абстракции, а не от конкретного вендора.
Провайдер получает подготовленный запрос и возвращает **сырой** текст; вся
проверка структуры и подстановка коммерческих данных выполняется кодом.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SectionSpec:
    """Раздел шаблона, который должен вернуть провайдер."""

    key: str
    title: str


@dataclass(frozen=True)
class GenerationRequest:
    """Запрос к AI-провайдеру.

    ``system_prompt`` — правила (один из контуров защиты, не гарантия);
    ``user_prompt`` — структурированные данные брифа и шаблона;
    ``sections`` — ожидаемые разделы (используются mock-провайдером и для
    инструкции по формату ответа).
    """

    system_prompt: str
    user_prompt: str
    sections: tuple[SectionSpec, ...]


@runtime_checkable
class AIProvider(Protocol):
    """Контракт провайдера: имя и генерация текста по запросу."""

    name: str

    def generate(self, request: GenerationRequest) -> str:
        """Вернуть сырой текст ответа или возбудить ``AIProviderError``."""
        ...

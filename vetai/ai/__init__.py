"""Фабрика AI-провайдеров (REQ-08).

Провайдер выбирается через переменную окружения ``AI_PROVIDER``
(``gigachat`` — внешний API; ``mock`` — безопасный локальный режим). Логика
приложения зависит только от абстракции ``AIProvider``, поэтому смена вендора
не требует правок домена.
"""

from __future__ import annotations

from vetai import config
from vetai.ai.base import AIProvider, GenerationRequest, SectionSpec
from vetai.ai.errors import AIConfigError, AIProviderError
from vetai.ai.mock_provider import MockProvider

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AIConfigError",
    "GenerationRequest",
    "SectionSpec",
    "MockProvider",
    "get_provider",
]


def get_provider(name: str | None = None) -> AIProvider:
    """Создать провайдера по имени или значению ``AI_PROVIDER``.

    Raises:
        AIConfigError: неизвестный провайдер или отсутствует ключ GigaChat.
    """
    resolved = (name or config.get_ai_provider_name()).strip().lower()

    if resolved == "mock":
        return MockProvider()

    if resolved == "gigachat":
        auth_key = config.get_gigachat_auth_key()
        if not auth_key:
            raise AIConfigError("GIGACHAT_AUTH_KEY не задан.")
        # Ленивый импорт: не тянем HTTP-зависимость, пока не выбран GigaChat.
        from vetai.ai.gigachat_provider import GigaChatProvider

        return GigaChatProvider(
            auth_key=auth_key,
            scope=config.get_gigachat_scope(),
            model=config.get_gigachat_model(),
            base_url=config.get_gigachat_base_url(),
            auth_url=config.get_gigachat_auth_url(),
            timeout=config.get_ai_timeout_seconds(),
            ca_bundle=config.get_gigachat_ca_bundle(),
        )

    raise AIConfigError(f"Неизвестный AI-провайдер: {resolved}")

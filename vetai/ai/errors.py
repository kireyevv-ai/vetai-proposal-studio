"""Доменные ошибки AI-провайдера.

Любой провайдер обязан приводить сбои к этим исключениям, чтобы UI показывал
понятное сообщение (REQ-35), а лог получал техническую категорию статуса
(``ok`` / ``timeout`` / ``rate_limit`` / ``empty`` / ``error``, REQ-30).

Разделение «провайдер ↔ домен» важно для независимости от вендора (REQ-08):
слой генерации ничего не знает про конкретный HTTP-код, только про доменный
класс ошибки.
"""

from __future__ import annotations


class AIProviderError(Exception):
    """Базовая ошибка обращения к AI-провайдеру.

    ``log_status`` — значение для ``generation_logs.status``; ``message`` —
    текст, безопасный для показа пользователю (без секретов и деталей сети).
    """

    log_status: str = "error"
    message: str = "Не удалось получить ответ от AI-провайдера. Попробуйте ещё раз."

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(detail or self.message)

    def user_message(self) -> str:
        """Сообщение для пользователя (без технических деталей и секретов)."""
        return self.message


class AIConfigError(AIProviderError):
    """Провайдер не настроен (нет ключа/неизвестный провайдер)."""

    log_status = "error"
    message = (
        "AI-провайдер не настроен. Укажите ключ доступа GigaChat "
        "(переменная окружения GIGACHAT_AUTH_KEY) или включите безопасный "
        "режим AI_PROVIDER=mock. Обратитесь к администратору проекта."
    )


class AITimeoutError(AIProviderError):
    """Превышено время ожидания ответа провайдера."""

    log_status = "timeout"
    message = (
        "AI-провайдер не ответил вовремя (таймаут). Черновик не создан, "
        "повторите генерацию позже."
    )


class AIAuthError(AIProviderError):
    """Ошибка авторизации (неверный/просроченный ключ)."""

    log_status = "error"
    message = (
        "Ошибка авторизации в AI-провайдере. Проверьте ключ доступа "
        "(GIGACHAT_AUTH_KEY)."
    )


class AIRateLimitError(AIProviderError):
    """Превышен лимит запросов."""

    log_status = "rate_limit"
    message = (
        "Превышен лимит запросов к AI-провайдеру. Подождите немного и "
        "повторите генерацию."
    )


class AINetworkError(AIProviderError):
    """Сетевая ошибка: нет соединения, недоступен хост."""

    log_status = "error"
    message = (
        "Не удалось соединиться с AI-провайдером (сетевая ошибка). Проверьте "
        "подключение и повторите генерацию."
    )


class AITLSError(AINetworkError):
    """Ошибка проверки TLS-сертификата.

    Проверка TLS намеренно **не** отключается; при необходимости укажите
    доверенный корневой сертификат Минцифры (GIGACHAT_CA_BUNDLE_FILE).
    """

    log_status = "error"
    message = (
        "Не удалось проверить TLS-сертификат AI-провайдера. Проверка "
        "сертификатов не отключается; укажите доверенный корневой сертификат "
        "Минцифры (GIGACHAT_CA_BUNDLE_FILE)."
    )


class AIEmptyResponseError(AIProviderError):
    """Провайдер вернул пустой ответ."""

    log_status = "empty"
    message = (
        "AI-провайдер вернул пустой ответ. Черновик не создан, попробуйте "
        "повторить генерацию."
    )


class AIStructureError(AIProviderError):
    """Ответ провайдера не удалось разобрать по разделам шаблона."""

    log_status = "error"
    message = (
        "AI-провайдер вернул ответ в неожиданном формате: разделы шаблона "
        "не распознаны. Черновик не создан, попробуйте повторить генерацию."
    )

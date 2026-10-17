"""Обезличивание текста перед логированием (REQ-30..REQ-32, REQ-34).

Логи промптов/ответов не должны содержать персональных данных, контактов и
секретов. Маскирование выполняется **до** записи в ``generation_logs``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Российские номера: +7/8 и варианты разделителей.
_PHONE_RE = re.compile(
    r"(?:\+7|8)[\s\-()]?\d{3}[\s\-()]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
)

_EMAIL_REPLACEMENT = "[email]"
_PHONE_REPLACEMENT = "[телефон]"
_CLIENT_REPLACEMENT = "[клиент]"
_SECRET_REPLACEMENT = "[секрет]"


def mask_secrets(text: str, secrets: Iterable[str] = ()) -> str:
    """Заменить секретные значения (ключи, токены) на плейсхолдер.

    Пустые значения игнорируются, чтобы не заменять весь текст.
    """
    masked = text or ""
    for secret in secrets:
        if secret and len(secret) >= 4:
            masked = masked.replace(secret, _SECRET_REPLACEMENT)
    return masked


def mask_text(
    text: str,
    client: str | None = None,
    secrets: Iterable[str] = (),
) -> str:
    """Убрать из текста персональные данные и секреты перед логированием.

    Порядок: сначала секреты, затем имя клиента, затем email и телефоны.
    """
    masked = mask_secrets(text or "", secrets)
    if client and client.strip():
        masked = masked.replace(client.strip(), _CLIENT_REPLACEMENT)
    masked = _EMAIL_RE.sub(_EMAIL_REPLACEMENT, masked)
    masked = _PHONE_RE.sub(_PHONE_REPLACEMENT, masked)
    return masked

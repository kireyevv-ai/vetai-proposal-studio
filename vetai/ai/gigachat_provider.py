"""Провайдер GigaChat через официальный REST API.

Используется официальный способ авторизации OAuth 2.0:

1. ``POST {auth_url}`` (по умолчанию ``.../api/v2/oauth``) с заголовком
   ``Authorization: Basic <ключ авторизации>``, ``RqUID`` и телом ``scope=...``.
   В ответ приходит ``access_token`` (действует ограниченное время).
2. ``POST {base_url}/v1/chat/completions`` с заголовком
   ``Authorization: Bearer <access_token>``.

Проверка TLS **включена всегда** (``verify=True``); при необходимости можно
лишь указать доверенный корневой сертификат Минцифры
(``GIGACHAT_CA_BUNDLE_FILE``), но не отключить проверку. Ключ и токен не
логируются (REQ-33, REQ-34) и не попадают в сообщения об ошибках.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import requests

from vetai.ai.base import GenerationRequest
from vetai.ai.errors import (
    AIAuthError,
    AIEmptyResponseError,
    AINetworkError,
    AIProviderError,
    AIRateLimitError,
    AITLSError,
    AITimeoutError,
)

_TEMPERATURE = 0.2
_MAX_TOKENS = 2000


class GigaChatProvider:
    """Клиент GigaChat API. Бесконечные повторы не выполняются (одна попытка)."""

    name = "gigachat"

    def __init__(
        self,
        auth_key: str,
        scope: str,
        model: str,
        base_url: str,
        auth_url: str,
        timeout: float,
        ca_bundle: Path | None = None,
    ) -> None:
        self._auth_key = auth_key
        self._scope = scope
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._auth_url = auth_url
        self._timeout = timeout
        self._verify: bool | str = str(ca_bundle) if ca_bundle else True

    # --- Публичный интерфейс ------------------------------------------------

    def generate(self, request: GenerationRequest) -> str:
        token = self._get_access_token()
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": _TEMPERATURE,
            "max_tokens": _MAX_TOKENS,
            "stream": False,
        }
        data = self._post(
            f"{self._base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        choices = data.get("choices") or []
        content = ""
        if choices:
            content = (choices[0].get("message") or {}).get("content") or ""
        if not content.strip():
            raise AIEmptyResponseError()
        return content

    # --- Внутреннее ---------------------------------------------------------

    def _get_access_token(self) -> str:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid4()),
            "Authorization": f"Basic {self._auth_key}",
        }
        data = self._post(
            self._auth_url, headers=headers, data={"scope": self._scope}
        )
        token = data.get("access_token")
        if not token:
            raise AIAuthError("Токен доступа не получен.")
        return str(token)

    def _post(self, url: str, headers: dict[str, str], **kwargs) -> dict:
        """Единственный HTTP-вызов с маппингом сбоев в доменные ошибки."""
        try:
            response = requests.post(
                url,
                headers=headers,
                timeout=self._timeout,
                verify=self._verify,
                **kwargs,
            )
        except requests.exceptions.SSLError as exc:
            raise AITLSError(str(exc)) from exc
        except requests.exceptions.Timeout as exc:
            raise AITimeoutError(str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise AINetworkError(str(exc)) from exc
        except requests.exceptions.RequestException as exc:
            raise AINetworkError(str(exc)) from exc

        if response.status_code in (401, 403):
            raise AIAuthError(f"HTTP {response.status_code}")
        if response.status_code == 429:
            raise AIRateLimitError("HTTP 429")
        if response.status_code >= 400:
            raise AIProviderError(f"HTTP {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise AIEmptyResponseError("Не удалось разобрать JSON ответа.") from exc

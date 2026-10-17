"""Тесты провайдера GigaChat без реальной сети (requests.post подменяется).

Проверяем: официальный OAuth (Basic → Bearer), маппинг сбоев в доменные ошибки
(REQ-35), ошибки авторизации/лимита/таймаута/сети/TLS/пустого ответа, и что
проверка TLS не отключается (REQ-08, REQ-33, REQ-34).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from vetai.ai import gigachat_provider as module
from vetai.ai.base import GenerationRequest, SectionSpec
from vetai.ai.errors import (
    AIAuthError,
    AIEmptyResponseError,
    AINetworkError,
    AIProviderError,
    AIRateLimitError,
    AITLSError,
    AITimeoutError,
)

_REQUEST = GenerationRequest(
    system_prompt="system",
    user_prompt="user",
    sections=(SectionSpec("task", "Задача"),),
)


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, bad_json: bool = False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("invalid json")
        return self._payload


def _make_provider(ca_bundle: Path | None = None) -> module.GigaChatProvider:
    return module.GigaChatProvider(
        auth_key="super-secret-key-1234",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        base_url="https://api.giga.chat",
        auth_url="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        timeout=5.0,
        ca_bundle=ca_bundle,
    )


def _patch_post(monkeypatch: pytest.MonkeyPatch, router):
    monkeypatch.setattr(module.requests, "post", router)


def test_successful_answer_and_oauth_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def router(url, headers=None, **kwargs):
        calls.append({"url": url, "headers": headers, "kwargs": kwargs})
        if "oauth" in url:
            return _FakeResponse(200, {"access_token": "TOKEN-abc"})
        return _FakeResponse(200, {"choices": [{"message": {"content": "Черновик"}}]})

    _patch_post(monkeypatch, router)
    result = _make_provider().generate(_REQUEST)

    assert result == "Черновик"
    assert len(calls) == 2
    # OAuth: Basic-ключ; chat: Bearer-токен.
    assert calls[0]["headers"]["Authorization"].startswith("Basic ")
    assert calls[1]["headers"]["Authorization"] == "Bearer TOKEN-abc"
    assert calls[0]["headers"]["RqUID"]
    # Проверка TLS включена (не отключена).
    assert calls[0]["kwargs"]["verify"] is True
    assert calls[1]["kwargs"]["verify"] is True


def test_ca_bundle_passed_as_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def router(url, headers=None, **kwargs):
        captured.update(kwargs)
        if "oauth" in url:
            return _FakeResponse(200, {"access_token": "T"})
        return _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})

    _patch_post(monkeypatch, router)
    _make_provider(ca_bundle=Path("C:/certs/ca.pem")).generate(_REQUEST)
    assert captured["verify"] == str(Path("C:/certs/ca.pem"))


def test_auth_error_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_post(monkeypatch, lambda *a, **k: _FakeResponse(401, {}))
    with pytest.raises(AIAuthError):
        _make_provider().generate(_REQUEST)


def test_rate_limit_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    def router(url, headers=None, **kwargs):
        if "oauth" in url:
            return _FakeResponse(200, {"access_token": "T"})
        return _FakeResponse(429, {})

    _patch_post(monkeypatch, router)
    with pytest.raises(AIRateLimitError):
        _make_provider().generate(_REQUEST)


def test_timeout_maps_to_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def router(*args, **kwargs):
        raise requests.exceptions.Timeout("slow")

    _patch_post(monkeypatch, router)
    with pytest.raises(AITimeoutError):
        _make_provider().generate(_REQUEST)


def test_ssl_error_maps_to_tls_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def router(*args, **kwargs):
        raise requests.exceptions.SSLError("cert")

    _patch_post(monkeypatch, router)
    with pytest.raises(AITLSError):
        _make_provider().generate(_REQUEST)


def test_connection_error_maps_to_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def router(*args, **kwargs):
        raise requests.exceptions.ConnectionError("down")

    _patch_post(monkeypatch, router)
    with pytest.raises(AINetworkError):
        _make_provider().generate(_REQUEST)


def test_server_error_maps_to_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def router(url, headers=None, **kwargs):
        if "oauth" in url:
            return _FakeResponse(200, {"access_token": "T"})
        return _FakeResponse(500, {})

    _patch_post(monkeypatch, router)
    with pytest.raises(AIProviderError):
        _make_provider().generate(_REQUEST)


def test_empty_choices_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def router(url, headers=None, **kwargs):
        if "oauth" in url:
            return _FakeResponse(200, {"access_token": "T"})
        return _FakeResponse(200, {"choices": []})

    _patch_post(monkeypatch, router)
    with pytest.raises(AIEmptyResponseError):
        _make_provider().generate(_REQUEST)


def test_missing_token_raises_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_post(monkeypatch, lambda *a, **k: _FakeResponse(200, {}))
    with pytest.raises(AIAuthError):
        _make_provider().generate(_REQUEST)


def test_bad_json_raises_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def router(url, headers=None, **kwargs):
        if "oauth" in url:
            return _FakeResponse(200, {"access_token": "T"})
        return _FakeResponse(200, bad_json=True)

    _patch_post(monkeypatch, router)
    with pytest.raises(AIEmptyResponseError):
        _make_provider().generate(_REQUEST)


def test_error_messages_never_contain_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_post(monkeypatch, lambda *a, **k: _FakeResponse(401, {}))
    with pytest.raises(AIAuthError) as excinfo:
        _make_provider().generate(_REQUEST)
    assert "super-secret-key-1234" not in str(excinfo.value)
    assert "super-secret-key-1234" not in excinfo.value.user_message()

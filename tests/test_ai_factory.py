"""Тесты выбора AI-провайдера и настроек конфигурации (REQ-08)."""

from __future__ import annotations

import pytest

from vetai import config
from vetai.ai import get_provider
from vetai.ai.errors import AIConfigError
from vetai.ai.mock_provider import MockProvider


def test_mock_provider_selected_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VETAI_DB_PATH", "unused.db")
    provider = get_provider("mock")
    assert isinstance(provider, MockProvider)
    assert provider.name == "mock"


def test_provider_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    assert get_provider().name == "mock"


def test_unknown_provider_raises() -> None:
    with pytest.raises(AIConfigError):
        get_provider("does-not-exist")


def test_gigachat_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "")
    with pytest.raises(AIConfigError):
        get_provider("gigachat")


def test_gigachat_with_key_builds_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "test-key-not-real")
    monkeypatch.setenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    provider = get_provider("gigachat")
    assert provider.name == "gigachat"


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIGACHAT_SCOPE", raising=False)
    monkeypatch.delenv("GIGACHAT_MODEL", raising=False)
    monkeypatch.delenv("AI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("GIGACHAT_CA_BUNDLE_FILE", raising=False)
    assert config.get_gigachat_scope() == config.DEFAULT_GIGACHAT_SCOPE
    assert config.get_gigachat_model() == config.DEFAULT_GIGACHAT_MODEL
    assert config.get_ai_timeout_seconds() == config.DEFAULT_AI_TIMEOUT_SECONDS
    assert config.get_gigachat_ca_bundle() is None


def test_invalid_timeout_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "not-a-number")
    assert config.get_ai_timeout_seconds() == config.DEFAULT_AI_TIMEOUT_SECONDS
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "-5")
    assert config.get_ai_timeout_seconds() == config.DEFAULT_AI_TIMEOUT_SECONDS

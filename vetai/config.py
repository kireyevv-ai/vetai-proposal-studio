"""Конфигурация приложения: пути и переменные окружения.

Секреты (API-ключи) читаются только из переменных окружения и никогда не
попадают в исходный код или репозиторий (REQ-33, REQ-34).
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv не обязателен для работы
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DATABASE_PATH = DATA_DIR / "vetai_proposal_studio.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

APP_TITLE = "VETAI Proposal Studio"


def get_database_path() -> Path:
    """Путь к файлу SQLite.

    Переопределяется переменной окружения ``VETAI_DB_PATH`` (используется
    в тестах и при необходимости вынести базу в другое место).
    """
    raw = os.getenv("VETAI_DB_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_DATABASE_PATH


# --- AI-провайдер (REQ-06, REQ-08, REQ-33) --------------------------------
#
# Секреты (GIGACHAT_AUTH_KEY) читаются ТОЛЬКО из переменных окружения и
# никогда не попадают в код, логи или репозиторий (REQ-33, REQ-34).

DEFAULT_AI_PROVIDER = "gigachat"
DEFAULT_GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
DEFAULT_GIGACHAT_MODEL = "GigaChat"
DEFAULT_GIGACHAT_BASE_URL = "https://gigachat.devices.sberbank.ru/api"
DEFAULT_GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
DEFAULT_AI_TIMEOUT_SECONDS = 60.0


def get_ai_provider_name() -> str:
    """Имя активного провайдера (``AI_PROVIDER``; по умолчанию ``gigachat``).

    Значение ``mock`` включает безопасный локальный провайдер для демонстрации
    и тестов без обращения к внешнему API.
    """
    return os.getenv("AI_PROVIDER", DEFAULT_AI_PROVIDER).strip() or DEFAULT_AI_PROVIDER


def get_gigachat_auth_key() -> str:
    """Ключ авторизации GigaChat из переменных окружения (REQ-33)."""
    return os.getenv("GIGACHAT_AUTH_KEY", "").strip()


def get_gigachat_scope() -> str:
    """Область доступа GigaChat (``GIGACHAT_API_PERS``/``_B2B``/``_CORP``)."""
    return os.getenv("GIGACHAT_SCOPE", "").strip() or DEFAULT_GIGACHAT_SCOPE


def get_gigachat_model() -> str:
    """Имя модели GigaChat (``GIGACHAT_MODEL``)."""
    return os.getenv("GIGACHAT_MODEL", "").strip() or DEFAULT_GIGACHAT_MODEL


def get_gigachat_base_url() -> str:
    """Базовый URL API GigaChat (``GIGACHAT_BASE_URL``)."""
    return os.getenv("GIGACHAT_BASE_URL", "").strip() or DEFAULT_GIGACHAT_BASE_URL


def get_gigachat_auth_url() -> str:
    """URL авторизации OAuth GigaChat (``GIGACHAT_AUTH_URL``)."""
    return os.getenv("GIGACHAT_AUTH_URL", "").strip() or DEFAULT_GIGACHAT_AUTH_URL


def get_gigachat_ca_bundle() -> Path | None:
    """Путь к корневому сертификату Минцифры (``GIGACHAT_CA_BUNDLE_FILE``).

    Проверка TLS **не отключается**: при необходимости можно лишь указать
    доверенный корневой сертификат (официальный способ Минцифры), но не
    ослабить проверку (см. AGENTS.md, раздел 4).
    """
    raw = os.getenv("GIGACHAT_CA_BUNDLE_FILE", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def get_ai_timeout_seconds() -> float:
    """Таймаут обращения к провайдеру в секундах (``AI_TIMEOUT_SECONDS``)."""
    raw = os.getenv("AI_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_AI_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_AI_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_AI_TIMEOUT_SECONDS

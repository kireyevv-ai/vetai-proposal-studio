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

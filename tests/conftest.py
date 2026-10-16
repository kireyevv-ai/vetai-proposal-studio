"""Общие фикстуры тестов."""

from __future__ import annotations

from pathlib import Path

import pytest

from vetai.db import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Путь к временной базе с инициализированной схемой."""
    path = tmp_path / "test.db"
    init_database(path)
    return path

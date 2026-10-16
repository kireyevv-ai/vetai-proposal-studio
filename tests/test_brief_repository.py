"""Тесты сохранения и восстановления брифов (REQ-01, REQ-36)."""

from __future__ import annotations

from pathlib import Path

from vetai.models import Brief
from vetai.repositories import brief_repository


def _brief(client: str = "ООО «Учебный клиент»") -> Brief:
    return Brief(
        client=client,
        task="Внедрить решение",
        services=["Внедрение решения (учебная)", "Сопровождение (учебная)"],
        deadlines="30 календарных дней",
        budget="250 000 руб.",
    )


def test_save_and_get_latest_brief(db_path: Path) -> None:
    brief_id = brief_repository.save_brief(_brief(), db_path=db_path)

    saved = brief_repository.get_latest_brief(db_path=db_path)

    assert saved is not None
    assert saved.id == brief_id
    assert saved.client == "ООО «Учебный клиент»"
    assert saved.task == "Внедрить решение"
    assert saved.services == [
        "Внедрение решения (учебная)",
        "Сопровождение (учебная)",
    ]
    assert saved.deadlines == "30 календарных дней"
    assert saved.budget == "250 000 руб."


def test_get_brief_by_id(db_path: Path) -> None:
    brief_id = brief_repository.save_brief(_brief(), db_path=db_path)
    assert brief_repository.get_brief(brief_id, db_path=db_path) is not None
    assert brief_repository.get_brief(9999, db_path=db_path) is None


def test_latest_brief_is_restored_after_new_connection(db_path: Path) -> None:
    brief_repository.save_brief(_brief("Первый клиент"), db_path=db_path)
    second_id = brief_repository.save_brief(_brief("Второй клиент"), db_path=db_path)

    restored = brief_repository.get_latest_brief(db_path=db_path)

    assert restored is not None
    assert restored.id == second_id
    assert restored.client == "Второй клиент"


def test_to_brief_roundtrip(db_path: Path) -> None:
    original = _brief("Клиент для roundtrip")
    brief_repository.save_brief(original, db_path=db_path)

    saved = brief_repository.get_latest_brief(db_path=db_path)
    assert saved is not None

    restored = brief_repository.to_brief(saved)
    assert restored.client == original.client
    assert restored.task == original.task
    assert restored.services == original.services
    assert restored.deadlines == original.deadlines
    assert restored.budget == original.budget


def test_no_brief_returns_none(db_path: Path) -> None:
    assert brief_repository.get_latest_brief(db_path=db_path) is None

"""Тесты прайса: хранение в копейках, валидация, архивирование, безопасное удаление.

REQ-10, REQ-12, REQ-26, REQ-28: деньги — целые копейки; удаление позиции
недопустимо, если она используется в сохранённых брифах.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vetai.models import Brief
from vetai.repositories import brief_repository, price_repository


def _add(name: str = "Аудит текущих процессов", kopeks: int = 50000,
         db_path: Path | None = None) -> int:
    return price_repository.add_price_item(name, kopeks, db_path=db_path)


def test_add_stores_price_as_integer_kopeks(db_path: Path) -> None:
    item_id = _add(db_path=db_path)

    item = price_repository.get_price_item(item_id, db_path=db_path)

    assert item is not None
    assert item.price_kopeks == 50000
    assert type(item.price_kopeks) is int  # не float


def test_add_and_list_preserves_order(db_path: Path) -> None:
    _add("Услуга Б", 20000, db_path=db_path)
    _add("Услуга А", 10000, db_path=db_path)

    items = price_repository.list_price_items(db_path=db_path)

    assert [item.name for item in items] == ["Услуга Б", "Услуга А"]


def test_add_rejects_negative_kopeks(db_path: Path) -> None:
    with pytest.raises(ValueError, match="отрицательной"):
        _add("Услуга с ошибкой", -1, db_path=db_path)
    assert price_repository.list_price_items(db_path=db_path) == []


def test_add_rejects_empty_name(db_path: Path) -> None:
    with pytest.raises(ValueError, match="название"):
        _add("   ", 10000, db_path=db_path)


def test_add_rejects_duplicate_active_name_case_insensitive(db_path: Path) -> None:
    _add("Аудит", 10000, db_path=db_path)
    with pytest.raises(ValueError, match="уже есть"):
        _add("аудит", 20000, db_path=db_path)


def test_update_changes_name_and_price(db_path: Path) -> None:
    item_id = _add(db_path=db_path)

    price_repository.update_price_item(
        item_id, "Консультация", 150000, db_path=db_path
    )

    item = price_repository.get_price_item(item_id, db_path=db_path)
    assert item is not None
    assert item.name == "Консультация"
    assert item.price_kopeks == 150000


def test_update_rejects_negative_price(db_path: Path) -> None:
    item_id = _add(db_path=db_path)
    with pytest.raises(ValueError, match="отрицательной"):
        price_repository.update_price_item(item_id, "Аудит", -5, db_path=db_path)


def test_update_rejects_duplicate_name(db_path: Path) -> None:
    _add("Аудит", 10000, db_path=db_path)
    other_id = _add("Сопровождение", 20000, db_path=db_path)
    with pytest.raises(ValueError, match="уже есть"):
        price_repository.update_price_item(other_id, "аудит", 20000, db_path=db_path)


def test_archive_hides_item_but_keeps_row(db_path: Path) -> None:
    item_id = _add(db_path=db_path)

    price_repository.set_archived(item_id, True, db_path=db_path)

    assert price_repository.list_price_items(db_path=db_path) == []
    archived = price_repository.list_price_items(
        db_path=db_path, include_archived=True
    )
    assert [item.id for item in archived] == [item_id]
    assert archived[0].is_active is False


def test_restore_archived_item(db_path: Path) -> None:
    item_id = _add(db_path=db_path)
    price_repository.set_archived(item_id, True, db_path=db_path)

    price_repository.set_archived(item_id, False, db_path=db_path)

    active = price_repository.list_price_items(db_path=db_path)
    assert [item.id for item in active] == [item_id]


def test_restore_rejected_when_name_taken(db_path: Path) -> None:
    first_id = _add("Аудит", 10000, db_path=db_path)
    second_id = _add("Сопровождение", 20000, db_path=db_path)
    price_repository.set_archived(second_id, True, db_path=db_path)
    price_repository.update_price_item(first_id, "Сопровождение", 10000, db_path=db_path)

    with pytest.raises(ValueError, match="уже есть"):
        price_repository.set_archived(second_id, False, db_path=db_path)


def test_delete_allowed_when_not_referenced(db_path: Path) -> None:
    item_id = _add(db_path=db_path)

    price_repository.delete_price_item(item_id, db_path=db_path)

    assert price_repository.get_price_item(item_id, db_path=db_path) is None


def test_delete_blocked_when_referenced_by_brief(db_path: Path) -> None:
    brief_repository.save_brief(
        Brief(
            client="ООО «Клиент»",
            task="Задача",
            services=["Аудит текущих процессов"],
            deadlines="30 дней",
            budget="100 000 руб.",
        ),
        db_path=db_path,
    )
    item_id = _add(db_path=db_path)

    with pytest.raises(ValueError, match="используется"):
        price_repository.delete_price_item(item_id, db_path=db_path)

    assert price_repository.get_price_item(item_id, db_path=db_path) is not None


def test_archive_of_referenced_service_keeps_brief_intact(db_path: Path) -> None:
    brief_repository.save_brief(
        Brief(
            client="ООО «Клиент»",
            task="Задача",
            services=["Аудит текущих процессов"],
            deadlines="30 дней",
            budget="100 000 руб.",
        ),
        db_path=db_path,
    )
    item_id = _add(db_path=db_path)

    price_repository.set_archived(item_id, True, db_path=db_path)

    saved = brief_repository.get_latest_brief(db_path=db_path)
    assert saved is not None
    assert saved.services == ["Аудит текущих процессов"]
    assert price_repository.list_price_items(db_path=db_path) == []


def test_is_referenced_is_case_insensitive(db_path: Path) -> None:
    brief_repository.save_brief(
        Brief(
            client="ООО «Клиент»",
            task="Задача",
            services=["аудит текущих ПРОЦЕССОВ"],
            deadlines="30 дней",
            budget="100 000 руб.",
        ),
        db_path=db_path,
    )
    assert price_repository.is_referenced_in_briefs(
        "Аудит текущих процессов", db_path=db_path
    )
    assert not price_repository.is_referenced_in_briefs(
        "Другая услуга", db_path=db_path
    )


def test_get_active_by_name_for_trusted_substitution(db_path: Path) -> None:
    item_id = _add("Аудит", 50000, db_path=db_path)

    found = price_repository.get_active_by_name("Аудит", db_path=db_path)
    assert found is not None
    assert found.id == item_id
    assert found.price_kopeks == 50000

    assert price_repository.get_active_by_name("Нет такой", db_path=db_path) is None

    price_repository.set_archived(item_id, True, db_path=db_path)
    assert price_repository.get_active_by_name("Аудит", db_path=db_path) is None

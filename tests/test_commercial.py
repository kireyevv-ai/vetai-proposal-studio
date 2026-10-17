"""Тесты программной подстановки коммерческих условий (REQ-10, REQ-12)."""

from __future__ import annotations

from pathlib import Path

from vetai.repositories import price_repository
from vetai.services import commercial
from vetai.validation import format_price, parse_price_to_kopeks


def _seed(db_path: Path) -> None:
    price_repository.add_price_item("Аудит", parse_price_to_kopeks("500.00"), db_path=db_path)
    price_repository.add_price_item(
        "Внедрение", parse_price_to_kopeks("1 200,50"), db_path=db_path
    )


def test_total_is_sum_of_kopeks(db_path: Path) -> None:
    _seed(db_path)
    data = commercial.build_commercial_data(
        ["Аудит", "Внедрение"], "30 дней", db_path=db_path
    )
    assert data.total_kopeks == 50000 + 120050
    assert data.missing == []
    assert data.deadlines_text == "30 дней"


def test_matching_is_case_insensitive(db_path: Path) -> None:
    _seed(db_path)
    data = commercial.build_commercial_data(["аудит"], "", db_path=db_path)
    assert data.missing == []
    assert data.items[0].price_kopeks == 50000


def test_unknown_service_has_no_price_and_no_total(db_path: Path) -> None:
    _seed(db_path)
    data = commercial.build_commercial_data(
        ["Аудит", "Несуществующая услуга"], "", db_path=db_path
    )
    assert data.total_kopeks is None
    assert data.missing == ["Несуществующая услуга"]


def test_price_section_uses_trusted_values(db_path: Path) -> None:
    _seed(db_path)
    data = commercial.build_commercial_data(["Аудит", "Внедрение"], "", db_path=db_path)
    text = commercial.render_price_section(data)
    assert format_price(50000) in text
    assert format_price(120050) in text
    assert f"Итого: {format_price(170050)}" in text


def test_missing_price_section_does_not_invent_total(db_path: Path) -> None:
    _seed(db_path)
    data = commercial.build_commercial_data(["Аудит", "Нет в прайсе"], "", db_path=db_path)
    text = commercial.render_price_section(data)
    assert "Итого:" not in text
    assert "не определена" in text


def test_deadline_section_comes_from_brief() -> None:
    assert (
        commercial.render_deadline_section("30 календарных дней")
        == "Сроки выполнения: 30 календарных дней."
    )
    assert (
        commercial.render_deadline_section("2 рабочих дня")
        == "Сроки выполнения: 2 рабочих дня."
    )
    assert "не указаны" in commercial.render_deadline_section("")


def test_deadline_section_does_not_guess_ambiguous_unit() -> None:
    # «45 дней» неоднозначно (рабочие или календарные) — единицу не присваиваем.
    text = commercial.render_deadline_section("45 дней")
    assert "45" in text
    assert "требует уточнения" in text
    assert "календарных" not in text
    assert "рабочих" not in text


def test_ambiguous_deadline_warns(db_path: Path) -> None:
    _seed(db_path)
    data = commercial.build_commercial_data(["Аудит"], "45 дней", db_path=db_path)
    assert data.deadlines_ambiguous is True
    assert any("единица измерения" in w.lower() for w in commercial.warnings_for(data))


def test_warnings_flag_missing_price_and_deadlines(db_path: Path) -> None:
    _seed(db_path)
    data = commercial.build_commercial_data(["Нет услуги"], "", db_path=db_path)
    warnings = commercial.warnings_for(data)
    assert any("Нет цены" in w for w in warnings)
    assert any("сроки" in w.lower() for w in warnings)

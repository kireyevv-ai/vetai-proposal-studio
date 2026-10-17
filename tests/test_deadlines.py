"""Тесты сроков: склонение, разбор и канонизация (Часть Б)."""

from __future__ import annotations

from vetai import deadlines


def test_format_deadline_declensions() -> None:
    assert deadlines.format_deadline(1, "calendar_days") == "1 календарный день"
    assert deadlines.format_deadline(2, "calendar_days") == "2 календарных дня"
    assert deadlines.format_deadline(5, "calendar_days") == "5 календарных дней"
    assert deadlines.format_deadline(11, "calendar_days") == "11 календарных дней"
    assert deadlines.format_deadline(21, "calendar_days") == "21 календарный день"
    assert deadlines.format_deadline(30, "calendar_days") == "30 календарных дней"
    assert deadlines.format_deadline(21, "work_days") == "21 рабочий день"
    assert deadlines.format_deadline(1, "weeks") == "1 неделя"
    assert deadlines.format_deadline(3, "months") == "3 месяца"


def test_parse_deadline_recognizes_units() -> None:
    assert deadlines.parse_deadline("30 календарных дней") == (30, "calendar_days")
    assert deadlines.parse_deadline("5 рабочих дней") == (5, "work_days")
    assert deadlines.parse_deadline("2 недели") == (2, "weeks")
    assert deadlines.parse_deadline("3 месяца") == (3, "months")


def test_parse_deadline_ambiguous_has_no_unit() -> None:
    assert deadlines.parse_deadline("30 дней") == (30, None)
    assert deadlines.parse_deadline("30") == (30, None)


def test_parse_deadline_empty_or_textual() -> None:
    assert deadlines.parse_deadline("") == (None, None)
    assert deadlines.parse_deadline("уточним позже") == (None, None)


def test_compose_deadline_requires_both_parts() -> None:
    assert deadlines.compose_deadline(30, "calendar_days") == "30 календарных дней"
    assert deadlines.compose_deadline(None, "calendar_days") == ""
    assert deadlines.compose_deadline(30, None) == ""


def test_normalize_deadline_keeps_ambiguous() -> None:
    assert deadlines.normalize_deadline("30 календарных дней") == "30 календарных дней"
    assert deadlines.normalize_deadline("30 дней") == "30 дней"
    assert deadlines.normalize_deadline("") == ""

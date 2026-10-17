"""Тесты разбора и форматирования цены (копейки, без float; REQ-10, REQ-26)."""

from __future__ import annotations

import pytest

from vetai.validation import format_price, parse_price_to_kopeks


@pytest.mark.parametrize(
    ("raw", "expected_kopeks"),
    [
        ("1500", 150000),
        ("1500.50", 150050),
        ("1500.5", 150050),
        ("1 500", 150000),
        ("1 500,50", 150050),
        ("1500,5", 150050),
        ("0", 0),
        ("0,99", 99),
        ("1500 руб.", 150000),
        ("1 500 руб", 150000),
        ("250 ₽", 25000),
        ("0.01", 1),
    ],
)
def test_parse_valid_prices_to_kopeks(raw: str, expected_kopeks: int) -> None:
    assert parse_price_to_kopeks(raw) == expected_kopeks


def test_parse_is_exact_unlike_float() -> None:
    # float дал бы 28.99...96 при умножении 0.29 * 100 — копейки должны быть точны.
    assert parse_price_to_kopeks("0.29") == 29
    assert parse_price_to_kopeks("0.07") == 7


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "abc", "1e3", "1.2.3", "10.999", "10,999", "--5", "15.о"],
)
def test_parse_rejects_invalid_numeric(raw: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_price_to_kopeks(raw)
    assert str(excinfo.value)


@pytest.mark.parametrize("raw", ["-1", "-0.01", "-1000,50"])
def test_parse_rejects_negative_prices(raw: str) -> None:
    with pytest.raises(ValueError, match="отрицательной"):
        parse_price_to_kopeks(raw)


@pytest.mark.parametrize(
    ("kopeks", "expected"),
    [
        (150000, "1 500 руб."),
        (150050, "1 500,50 руб."),
        (99, "0,99 руб."),
        (0, "0 руб."),
        (123456789, "1 234 567,89 руб."),
    ],
)
def test_format_price(kopeks: int, expected: str) -> None:
    assert format_price(kopeks) == expected


def test_format_parse_roundtrip() -> None:
    assert parse_price_to_kopeks(format_price(150050)) == 150050
    assert parse_price_to_kopeks(format_price(150000)) == 150000

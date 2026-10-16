"""Тесты валидации брифа (REQ-02..REQ-05)."""

from __future__ import annotations

import pytest

from vetai.models import Brief
from vetai.validation import is_brief_valid, validate_brief


def _valid_brief() -> Brief:
    return Brief(
        client="ООО «Учебный клиент»",
        task="Внедрить решение",
        services=["Внедрение решения (учебная)"],
        deadlines="30 календарных дней",
        budget="250 000 руб.",
    )


def test_valid_brief_has_no_errors() -> None:
    brief = _valid_brief()
    assert validate_brief(brief) == []
    assert is_brief_valid(brief) is True


def test_whitespace_only_client_is_invalid() -> None:
    brief = _valid_brief()
    brief.client = "   "
    assert is_brief_valid(brief) is False


@pytest.mark.parametrize(
    "field",
    ["client", "task", "services", "deadlines", "budget"],
)
def test_each_missing_required_field_blocks_generation(field: str) -> None:
    brief = _valid_brief()
    setattr(brief, field, [] if field == "services" else "")
    errors = validate_brief(brief)
    assert errors, f"Поле {field} должно делать бриф невалидным"
    assert is_brief_valid(brief) is False


def test_empty_services_list_is_invalid() -> None:
    brief = _valid_brief()
    brief.services = []
    assert any("услуг" in message for message in validate_brief(brief))

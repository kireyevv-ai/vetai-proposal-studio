"""Тесты сборки промпта и разбора ответа (REQ-06, REQ-09, REQ-13)."""

from __future__ import annotations

from vetai.ai.base import SectionSpec
from vetai.models import Brief
from vetai.services import prompt_builder


def _brief() -> Brief:
    return Brief(
        client="ООО «Учебный клиент»",
        task="Внедрить решение",
        services=["Аудит"],
        deadlines="30 календарных дней",
        budget="250 000 руб.",
    )


def test_user_prompt_contains_only_model_sections() -> None:
    sections = (
        SectionSpec(key="task", title="Описание задачи"),
        SectionSpec(key="scope", title="Состав работ и услуги"),
    )
    request = prompt_builder.build_request(_brief(), sections)

    assert "task" in request.user_prompt
    assert "scope" in request.user_prompt
    assert "pricing" not in request.user_prompt
    assert "deadlines" not in request.user_prompt
    assert request.sections == sections


def test_user_prompt_omits_commercial_and_budget_data() -> None:
    sections = (SectionSpec(key="task", title="Описание задачи"),)
    request = prompt_builder.build_request(_brief(), sections)

    # Сроки и бюджет модели не передаются вовсе (REQ-10, REQ-11, REQ-12).
    assert "календарных" not in request.user_prompt
    assert "250 000" not in request.user_prompt
    # Роли заказчика и исполнителя различены (Часть А, п. 1).
    assert "Заказчик" in request.user_prompt
    assert "Услуги исполнителя" in request.user_prompt


def test_system_prompt_forbids_unconfirmed_claims() -> None:
    text = prompt_builder.SYSTEM_PROMPT.lower()
    for marker in ("опыт", "гаранти", "обязательств", "заказчик", "исполнител"):
        assert marker in text


def test_parse_sections_returns_key_to_text() -> None:
    raw = (
        "[[SECTION: task]]\nТекст задачи\n[[/SECTION]]\n"
        "[[SECTION: scope]]\nСостав работ\n[[/SECTION]]"
    )
    assert prompt_builder.parse_sections(raw) == {
        "task": "Текст задачи",
        "scope": "Состав работ",
    }


def test_parse_sections_empty_for_unparsable() -> None:
    assert prompt_builder.parse_sections("") == {}
    assert prompt_builder.parse_sections("нет блоков") == {}

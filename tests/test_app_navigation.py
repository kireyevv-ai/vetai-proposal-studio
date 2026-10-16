"""Тест запуска приложения и навигации по четырём экранам.

Проверяет, что приложение стартует, доступны все четыре экрана и что
нереализованные экраны сообщают о своём статусе (критерий B).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import vetai.services.training_catalog as training_catalog

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppTest:
    monkeypatch.setenv("VETAI_DB_PATH", str(tmp_path / "app_test.db"))
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    return at


def test_app_starts_without_error(app: AppTest) -> None:
    assert not app.exception


def test_four_screens_available(app: AppTest) -> None:
    assert list(app.radio[0].options) == [
        "Бриф",
        "Черновик",
        "Предпросмотр и PDF",
        "История КП",
    ]


def test_brief_screen_has_form(app: AppTest) -> None:
    labels = [block.label for block in app.text_input] + [
        block.label for block in app.text_area
    ]
    assert "Название клиента *" in labels
    assert "Описание задачи *" in labels
    assert app.multiselect[0].label == "Услуги * (минимум одна)"


def test_brief_multiselect_uses_training_catalog(app: AppTest) -> None:
    assert list(app.multiselect[0].options) == training_catalog.service_names()


def test_generation_blocked_when_brief_incomplete(app: AppTest) -> None:
    generate_button = app.button[1]
    assert generate_button.label == "Сгенерировать черновик"
    assert generate_button.disabled is True


def test_generation_enabled_when_brief_valid(app: AppTest) -> None:
    app.text_input(key="brief_client").set_value("ООО «Учебный клиент»")
    app.text_area(key="brief_task").set_value("Внедрить решение")
    app.multiselect(key="brief_services").set_value(
        [training_catalog.service_names()[0]]
    )
    app.text_input(key="brief_deadlines").set_value("30 дней")
    app.text_input(key="brief_budget").set_value("100 000 руб.")
    app.run()

    assert app.button[1].disabled is False


def test_incomplete_brief_shows_error_on_save(app: AppTest) -> None:
    app.text_input(key="brief_client").set_value("Клиент без остальных полей")
    app.button[0].click().run()

    assert app.button[0].label == "Сохранить бриф"
    assert any("не сохранён" in err.value.lower() for err in app.error)


def test_valid_brief_is_saved(app: AppTest) -> None:
    app.text_input(key="brief_client").set_value("ООО «Учебный клиент»")
    app.text_area(key="brief_task").set_value("Внедрить решение")
    app.multiselect(key="brief_services").set_value(
        [training_catalog.service_names()[0]]
    )
    app.text_input(key="brief_deadlines").set_value("30 дней")
    app.text_input(key="brief_budget").set_value("100 000 руб.")
    app.run()
    app.button[0].click().run()

    assert any("сохранён" in msg.value.lower() for msg in app.success)


@pytest.mark.parametrize(
    ("screen", "marker"),
    [
        ("Черновик", "разработке"),
        ("Предпросмотр и PDF", "разработке"),
        ("История КП", "разработке"),
    ],
)
def test_unimplemented_screens_report_status(
    app: AppTest, screen: str, marker: str
) -> None:
    app.radio[0].set_value(screen)
    app.run()

    assert not app.exception
    assert any(marker in warn.value.lower() for warn in app.warning)

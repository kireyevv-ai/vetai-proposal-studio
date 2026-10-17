"""Тест запуска приложения и навигации по экранам.

Проверяет, что приложение стартует, доступны четыре экрана ТЗ школы и экран
«Настройки», что бриф выбирает услуги из прайса и что нереализованные экраны
сообщают о своём статусе (критерий B).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from vetai.db import init_database
from vetai.repositories import price_repository

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

SEED_PRICES: list[tuple[str, int]] = [
    ("Аудит текущих процессов", 50000),
    ("Консультация по задаче", 15000),
    ("Внедрение решения", 120000),
]


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppTest:
    db = tmp_path / "app_test.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(db))
    init_database(db)
    for name, kopeks in SEED_PRICES:
        price_repository.add_price_item(name, kopeks, db_path=db)
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    return at


def test_app_starts_without_error(app: AppTest) -> None:
    assert not app.exception


def test_four_school_screens_plus_settings_available(app: AppTest) -> None:
    assert list(app.radio[0].options) == [
        "Бриф",
        "Черновик",
        "Предпросмотр и PDF",
        "История КП",
        "Настройки",
    ]


def test_brief_screen_has_form(app: AppTest) -> None:
    labels = [block.label for block in app.text_input] + [
        block.label for block in app.text_area
    ]
    assert "Название клиента *" in labels
    assert "Описание задачи *" in labels
    assert app.multiselect[0].label == "Услуги * (минимум одна)"
    # Сроки вводятся как число + единица измерения (Часть Б).
    assert app.number_input[0].label == "Сроки: значение *"
    assert app.selectbox[0].label == "Сроки: единица измерения *"


def test_brief_multiselect_uses_price_list(app: AppTest) -> None:
    assert list(app.multiselect[0].options) == [name for name, _ in SEED_PRICES]


def test_generation_blocked_when_brief_incomplete(app: AppTest) -> None:
    generate_button = app.button[1]
    assert generate_button.label == "Сгенерировать КП"
    assert generate_button.disabled is True


def test_generation_enabled_when_brief_valid(app: AppTest) -> None:
    app.text_input(key="brief_client").set_value("ООО «Учебный клиент»")
    app.text_area(key="brief_task").set_value("Внедрить решение")
    app.multiselect(key="brief_services").set_value([SEED_PRICES[0][0]])
    app.number_input(key="brief_deadline_value").set_value(30)
    app.selectbox(key="brief_deadline_unit").select("календарные дни")
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
    app.multiselect(key="brief_services").set_value([SEED_PRICES[0][0]])
    app.number_input(key="brief_deadline_value").set_value(30)
    app.selectbox(key="brief_deadline_unit").select("календарные дни")
    app.text_input(key="brief_budget").set_value("100 000 руб.")
    app.run()
    app.button[0].click().run()

    assert any("сохранён" in msg.value.lower() for msg in app.success)


def test_brief_with_empty_price_list_shows_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("VETAI_DB_PATH", str(tmp_path / "empty_prices.db"))
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()

    assert not at.exception
    assert list(at.multiselect[0].options) == []
    assert any("прайс пуст" in info.value.lower() for info in at.info)


@pytest.mark.parametrize(
    ("screen", "marker"),
    [
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

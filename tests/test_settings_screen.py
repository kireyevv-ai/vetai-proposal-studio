"""Тесты экрана «Настройки»: прайс и шаблон КП (REQ-26..REQ-29, OQ-02)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from vetai.db import connect, init_database
from vetai.models import Brief
from vetai.repositories import brief_repository, price_repository

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

SEED_PRICES: list[tuple[str, int]] = [
    ("Аудит текущих процессов", 50000),
    ("Консультация по задаче", 15000),
]


def _click(app: AppTest, key: str) -> AppTest:
    """Нажать кнопку/кнопку формы и выполнить прогон."""
    widget = next(button for button in app.button if button.key == key)
    widget.click()
    return app.run()


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppTest:
    db = tmp_path / "settings_test.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(db))
    init_database(db)
    for name, kopeks in SEED_PRICES:
        price_repository.add_price_item(name, kopeks, db_path=db)
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.radio[0].set_value("Настройки")
    at.run()
    assert not at.exception
    return at


def test_settings_screen_has_two_tabs(app: AppTest) -> None:
    assert [tab.label for tab in app.tabs] == ["Услуги и цены", "Шаблон КП"]


def test_price_list_shows_seeded_items(app: AppTest) -> None:
    labels = [expander.label for expander in app.expander]
    assert "Аудит текущих процессов — 500 руб." in labels
    assert "Консультация по задаче — 150 руб." in labels


def test_add_price_item(app: AppTest) -> None:
    app.text_input(key="price_add_name").set_value("Внедрение решения")
    app.text_input(key="price_add_price").set_value("1 500,50")
    _click(app, "price_add_submit")

    assert not app.exception
    assert any(
        "Добавлено: Внедрение решения — 1 500,50 руб." in msg.value
        for msg in app.success
    )
    app.run()  # перерисовать список прайса (заголовок рендерится выше обработчика)
    assert any("Внедрение решения" in expander.label for expander in app.expander)


def test_add_price_rejects_negative_price(app: AppTest) -> None:
    app.text_input(key="price_add_name").set_value("Плохая услуга")
    app.text_input(key="price_add_price").set_value("-100")
    _click(app, "price_add_submit")

    assert any("отрицательной" in err.value for err in app.error)
    assert not any(
        "Плохая услуга" in expander.label for expander in app.expander
    )


def test_add_price_rejects_invalid_numeric(app: AppTest) -> None:
    app.text_input(key="price_add_name").set_value("Плохая услуга")
    app.text_input(key="price_add_price").set_value("сто рублей")
    _click(app, "price_add_submit")

    assert any("Цена должна быть числом" in err.value for err in app.error)


def test_edit_price_item(app: AppTest) -> None:
    app.text_input(key="price_name_1").set_value("Аудит (новый)")
    app.text_input(key="price_value_1").set_value("750")
    _click(app, "price_edit_submit_1")

    assert any("Позиция сохранена" in msg.value for msg in app.success)
    app.run()  # перерисовать заголовки expander
    assert any(
        "Аудит (новый) — 750 руб." in expander.label
        for expander in app.expander
    )


def test_delete_disabled_for_service_used_in_briefs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "referenced.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(db))
    init_database(db)
    price_repository.add_price_item("Аудит текущих процессов", 50000, db_path=db)
    brief_repository.save_brief(
        Brief(
            client="ООО «Клиент»",
            task="Задача",
            services=["Аудит текущих процессов"],
            deadlines="30 дней",
            budget="100 000 руб.",
        ),
        db_path=db,
    )
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.radio[0].set_value("Настройки")
    at.run()

    delete_button = next(
        button for button in at.button if button.key == "price_delete_1"
    )
    archive_button = next(
        button for button in at.button if button.key == "price_archive_1"
    )
    assert delete_button.disabled is True
    assert archive_button.disabled is False


def test_archived_item_hidden_from_list_and_restorable(app: AppTest) -> None:
    _click(app, "price_archive_1")

    assert any("перемещена в архив" in msg.value for msg in app.success)
    app.run()  # перерисовать список: архивная позиция уходит из активного списка
    assert not any(
        expander.label.startswith("Аудит текущих процессов —")
        for expander in app.expander
    )

    app.checkbox(key="price_show_archived").set_value(True)
    app.run()
    assert any(
        "Аудит текущих процессов" in expander.label
        and "в архиве" in expander.label
        for expander in app.expander
    )

    _click(app, "price_restore_1")
    assert any("возвращена в прайс" in msg.value for msg in app.success)


def test_template_default_sections_listed(app: AppTest) -> None:
    text_keys = {widget.key for widget in app.text_input}
    assert {"tpl_title_about", "tpl_title_task", "tpl_title_scope",
            "tpl_title_deadlines", "tpl_title_pricing",
            "tpl_title_terms"} <= text_keys
    assert [section["key"] for section in app.session_state["tpl_sections"]] == [
        "about", "task", "scope", "deadlines", "pricing", "terms",
    ]


def test_mandatory_sections_cannot_be_deleted(app: AppTest) -> None:
    buttons = {button.key: button for button in app.button}
    assert buttons["tpl_delete_task"].disabled is True
    assert buttons["tpl_delete_pricing"].disabled is True
    assert buttons["tpl_delete_about"].disabled is False


def test_reorder_section_moves_it(app: AppTest) -> None:
    _click(app, "tpl_down_about")

    keys = [section["key"] for section in app.session_state["tpl_sections"]]
    assert keys[:3] == ["task", "about", "scope"]
    assert not app.exception


def test_first_section_cannot_move_up(app: AppTest) -> None:
    buttons = {button.key: button for button in app.button}
    assert buttons["tpl_up_about"].disabled is True
    assert buttons["tpl_up_task"].disabled is False


def test_add_section_and_save(app: AppTest) -> None:
    app.text_input(key="tpl_new_title").set_value("Порядок оплаты")
    _click(app, "tpl_add_section_submit")

    keys = [section["key"] for section in app.session_state["tpl_sections"]]
    assert keys[-1] == "custom_1"

    _click(app, "tpl_save")
    assert any("Шаблон сохранён" in msg.value for msg in app.success)
    assert not app.exception


def test_save_rejects_empty_mandatory_title(app: AppTest) -> None:
    app.text_input(key="tpl_title_task").set_value("   ")
    _click(app, "tpl_save")

    assert any(
        "Шаблон не сохранён" in err.value and "пустой заголовок" in err.value
        for err in app.error
    )


def test_reset_restores_saved_titles(app: AppTest) -> None:
    app.text_input(key="tpl_title_about").set_value("Изменённый заголовок")
    app.run()
    assert (
        app.text_input(key="tpl_title_about").value == "Изменённый заголовок"
    )

    _click(app, "tpl_reset")

    assert (
        app.text_input(key="tpl_title_about").value == "О компании"
    )
    titles = [section["title"] for section in app.session_state["tpl_sections"]]
    assert "Изменённый заголовок" not in titles


def test_saved_template_survives_app_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "restart.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(db))
    init_database(db)

    first = AppTest.from_file(str(APP_PATH), default_timeout=30)
    first.run()
    first.radio[0].set_value("Настройки")
    first.run()
    first.text_input(key="tpl_title_about").set_value("О компании и опыте")
    next(
        button for button in first.button if button.key == "tpl_save"
    ).click().run()
    assert any("Шаблон сохранён" in msg.value for msg in first.success)

    second = AppTest.from_file(str(APP_PATH), default_timeout=30)
    second.run()
    second.radio[0].set_value("Настройки")
    second.run()

    assert not second.exception
    assert (
        second.text_input(key="tpl_title_about").value == "О компании и опыте"
    )
    assert any(
        "О компании и опыте" in section["title"]
        for section in second.session_state["tpl_sections"]
    )


def test_brief_form_uses_price_and_keeps_archived_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "brief_archive.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(db))
    init_database(db)
    price_repository.add_price_item("Аудит", 50000, db_path=db)
    price_repository.add_price_item("Сопровождение", 90000, db_path=db)
    brief_repository.save_brief(
        Brief(
            client="ООО «Клиент»",
            task="Задача",
            services=["Аудит", "Сопровождение"],
            deadlines="30 дней",
            budget="100 000 руб.",
        ),
        db_path=db,
    )
    item_id = price_repository.list_price_items(db_path=db)[1].id
    price_repository.set_archived(item_id, True, db_path=db)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()

    assert not at.exception
    options = list(at.multiselect[0].options)
    assert "Аудит" in options
    assert "Сопровождение" in options  # сохранённый выбор не теряется
    assert at.multiselect[0].value == ["Аудит", "Сопровождение"]
    assert any("архиве прайса" in caption.value for caption in at.caption)

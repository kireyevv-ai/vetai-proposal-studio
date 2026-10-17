"""Сквозные сценарии приёмки этапа №3 (регрессия).

Воспроизводит четыре пользовательских сценария, не принятых на этапе №3, и
проверяет гарантии A–G. Тесты работают на отдельной временной БД (``tmp_path``)
через переменную окружения ``VETAI_DB_PATH`` и не затрагивают пользовательскую
базу. «Перезагрузка страницы» моделируется новым экземпляром ``AppTest`` (новая
сессия Streamlit с тем же файлом базы).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from vetai.db import connect, init_database
from vetai.models import DEFAULT_TEMPLATE_SECTIONS
from vetai.repositories import brief_repository, price_repository

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

SERVICE_A = "Аудит текущих процессов"
SERVICE_B = "Консультация по задаче"
SEED_PRICES: list[tuple[str, int]] = [(SERVICE_A, 50000), (SERVICE_B, 15000)]

BRIEF_FIELDS = {
    "brief_client": "ООО «Учебный клиент»",
    "brief_budget": "100 000 руб.",
}
BRIEF_TASK = "Внедрить решение"
DEADLINE_VALUE = 30
DEADLINE_UNIT = "календарные дни"
DEADLINE_TEXT = "30 календарных дней"


@pytest.fixture
def db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "user_scenarios.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(path))
    init_database(path)
    for name, kopeks in SEED_PRICES:
        price_repository.add_price_item(name, kopeks, db_path=path)
    return path


def _new_app() -> AppTest:
    """Новый экземпляр приложения (пустая сессия — как перезагрузка страницы)."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    return at


def _goto(at: AppTest, screen: str) -> AppTest:
    at.radio[0].set_value(screen)
    return at.run()


def _button(at: AppTest, key: str):
    return next(button for button in at.button if button.key == key)


def _click(at: AppTest, key: str) -> AppTest:
    _button(at, key).click()
    return at.run()


def _click_label(at: AppTest, label: str) -> AppTest:
    next(button for button in at.button if button.label == label).click()
    return at.run()


def _keys(at: AppTest) -> list[str]:
    return [section["key"] for section in at.session_state["tpl_sections"]]


def _captions(at: AppTest) -> list[str]:
    return [caption.value for caption in at.caption]


def _infos(at: AppTest) -> list[str]:
    return [info.value for info in at.info]


def _fill_brief(at: AppTest, services: list[str]) -> None:
    for key, value in BRIEF_FIELDS.items():
        at.text_input(key=key).set_value(value)
    at.text_area(key="brief_task").set_value(BRIEF_TASK)
    at.multiselect(key="brief_services").set_value(services)
    at.number_input(key="brief_deadline_value").set_value(DEADLINE_VALUE)
    at.selectbox(key="brief_deadline_unit").select(DEADLINE_UNIT)
    at.run()


# --- Сценарий 4: названия и порядок разделов шаблона (A, B) ---------------


def test_A_B_template_titles_and_order_persist_after_save_and_restart(
    db_path: Path,
) -> None:
    first = _new_app()
    _goto(first, "Настройки")

    # Правка заголовка и порядка в одном прогоне (как в браузере: изменил и нажал).
    first.text_input(key="tpl_title_about").set_value("О компании и опыте")
    _click(first, "tpl_down_about")

    assert _keys(first)[:3] == ["task", "about", "scope"]
    assert first.text_input(key="tpl_title_about").value == "О компании и опыте"
    # Индикатор предупреждает: изменения ещё не в базе.
    assert any("несохранённые изменения" in value.lower() for value in _infos(first))

    _click(first, "tpl_save")
    assert any("Шаблон сохранён" in msg.value for msg in first.success)
    # После сохранения индикатор подтверждает запись.
    assert any(
        "совпадают с сохранёнными" in value for value in _captions(first)
    )

    # Перезагрузка страницы: новая сессия читает структуру из базы.
    second = _new_app()
    _goto(second, "Настройки")
    assert not second.exception
    assert _keys(second)[:3] == ["task", "about", "scope"]
    about = next(
        section
        for section in second.session_state["tpl_sections"]
        if section["key"] == "about"
    )
    assert about["title"] == "О компании и опыте"
    assert second.text_input(key="tpl_title_about").value == "О компании и опыте"


def test_template_changes_without_save_are_not_persisted(db_path: Path) -> None:
    first = _new_app()
    _goto(first, "Настройки")
    _click(first, "tpl_down_about")
    assert _keys(first)[:3] == ["task", "about", "scope"]

    # Без нажатия «Сохранить шаблон» правки не попадают в базу.
    second = _new_app()
    _goto(second, "Настройки")
    assert _keys(second) == [section.key for section in DEFAULT_TEMPLATE_SECTIONS]


# --- Сценарий 5: запрет удаления обязательных разделов (C) ----------------


def test_C_mandatory_sections_marked_and_delete_forbidden(db_path: Path) -> None:
    at = _new_app()
    _goto(at, "Настройки")

    marked = [value for value in _captions(at) if "обязательный раздел" in value]
    assert len(marked) == len(
        [s for s in DEFAULT_TEMPLATE_SECTIONS if s.mandatory]
    )

    assert _button(at, "tpl_delete_task").disabled is True
    assert _button(at, "tpl_delete_pricing").disabled is True
    assert _button(at, "tpl_delete_about").disabled is False

    # Невозможность нажать disabled-кнопку — как в браузере.
    with pytest.raises(Exception, match="disabled"):
        _button(at, "tpl_delete_task").click()
    assert "task" in _keys(at)

    # Необязательный раздел удаляется штатно.
    _click(at, "tpl_delete_about")
    assert "about" not in _keys(at)


# --- Сценарий 6: сохранение брифа и восстановление после перезагрузки (D) --


def test_D_brief_saved_via_ui_restored_after_restart(db_path: Path) -> None:
    first = _new_app()
    assert any(
        "кнопкой «Сохранить бриф»" in value for value in _captions(first)
    )
    _fill_brief(first, [SERVICE_A])
    _click_label(first, "Сохранить бриф")
    assert any("Бриф сохранён" in msg.value for msg in first.success)

    second = _new_app()  # перезагрузка страницы
    assert not second.exception
    assert second.text_input(key="brief_client").value == BRIEF_FIELDS["brief_client"]
    assert second.text_area(key="brief_task").value == BRIEF_TASK
    assert second.multiselect(key="brief_services").value == [SERVICE_A]
    assert second.number_input(key="brief_deadline_value").value == DEADLINE_VALUE
    assert second.selectbox(key="brief_deadline_unit").value == DEADLINE_UNIT
    assert second.text_input(key="brief_budget").value == BRIEF_FIELDS["brief_budget"]
    assert any(
        "Восстановлен последний сохранённый бриф" in value for value in _infos(second)
    )


def test_brief_not_restored_when_never_saved(db_path: Path) -> None:
    first = _new_app()
    _fill_brief(first, [SERVICE_A])
    # Бриф не сохраняли — после перезагрузки восстанавливать нечего.
    second = _new_app()
    assert second.text_input(key="brief_client").value == ""
    assert second.multiselect(key="brief_services").value == []
    assert not any(
        "Восстановлен последний сохранённый бриф" in value for value in _infos(second)
    )


# --- Сценарий 7: архивирование услуги и сохранность брифа (E) -------------


def test_E_archived_service_kept_in_saved_brief_but_hidden_for_new(
    db_path: Path,
) -> None:
    first = _new_app()
    _fill_brief(first, [SERVICE_A])
    _click_label(first, "Сохранить бриф")
    assert any("Бриф сохранён" in msg.value for msg in first.success)

    _goto(first, "Настройки")
    item_id = next(
        item.id
        for item in price_repository.list_price_items(db_path=db_path)
        if item.name == SERVICE_A
    )
    # Использованная в брифе услуга не удаляется — доступно только архивирование.
    assert _button(first, f"price_delete_{item_id}").disabled is True
    _click(first, f"price_archive_{item_id}")
    assert any("перемещена в архив" in msg.value for msg in first.success)

    second = _new_app()  # перезагрузка после архивирования
    assert second.multiselect(key="brief_services").value == [SERVICE_A]
    assert SERVICE_A in list(second.multiselect(key="brief_services").options)
    assert any("архиве прайса" in value for value in _captions(second))

    # Для нового выбора архивная услуга не предлагается.
    second.multiselect(key="brief_services").set_value([])
    second.run()
    options = list(second.multiselect(key="brief_services").options)
    assert SERVICE_A not in options
    assert SERVICE_B in options


# --- F: операции прайса продолжают работать (регрессия) -------------------


def test_F_price_operations_still_work(db_path: Path) -> None:
    at = _new_app()
    _goto(at, "Настройки")

    at.text_input(key="price_add_name").set_value("Внедрение решения")
    at.text_input(key="price_add_price").set_value("1 500,50")
    _click(at, "price_add_submit")
    assert any(
        "Добавлено: Внедрение решения — 1 500,50 руб." in msg.value
        for msg in at.success
    )

    item_id = next(
        item.id
        for item in price_repository.list_price_items(db_path=db_path)
        if item.name == "Внедрение решения"
    )
    at.text_input(key=f"price_name_{item_id}").set_value("Внедрение (новое)")
    at.text_input(key=f"price_value_{item_id}").set_value("2000")
    _click(at, f"price_edit_submit_{item_id}")
    assert any("Позиция сохранена" in msg.value for msg in at.success)

    _click(at, f"price_archive_{item_id}")
    at.run()
    assert not any(
        expander.label.startswith("Внедрение (новое) —")
        for expander in at.expander
    )
    at.checkbox(key="price_show_archived").set_value(True)
    at.run()
    assert any(
        "Внедрение (новое)" in expander.label and "в архиве" in expander.label
        for expander in at.expander
    )
    _click(at, f"price_restore_{item_id}")
    assert any("возвращена в прайс" in msg.value for msg in at.success)


# --- G: миграция не приводит к потере данных ------------------------------


def test_G_repeated_init_keeps_brief_and_price_data(db_path: Path) -> None:
    first = _new_app()
    _fill_brief(first, [SERVICE_A])
    _click_label(first, "Сохранить бриф")

    # Повторная инициализация (как при следующем запуске приложения) безопасна.
    init_database(db_path)
    init_database(db_path)

    conn = connect(db_path)
    try:
        price_type = next(
            column["type"]
            for column in conn.execute("PRAGMA table_info(price_items)").fetchall()
            if column["name"] == "price"
        )
        brief_count = conn.execute("SELECT COUNT(*) AS n FROM briefs").fetchone()["n"]
    finally:
        conn.close()

    assert price_type.upper().startswith("INTEGER")
    assert brief_count == 1
    saved = brief_repository.get_latest_brief(db_path=db_path)
    assert saved is not None
    assert saved.client == BRIEF_FIELDS["brief_client"]
    assert saved.services == [SERVICE_A]
    # Сроки хранятся в каноничном виде «число + единица» (Часть Б).
    assert saved.deadlines == DEADLINE_TEXT


# --- Часть Б: старая неоднозначная запись срока не переинтерпретируется -----


def test_legacy_ambiguous_deadline_is_not_auto_assigned(db_path: Path) -> None:
    from vetai.models import Brief

    brief_repository.save_brief(
        Brief(
            client=BRIEF_FIELDS["brief_client"],
            task=BRIEF_TASK,
            services=[SERVICE_A],
            deadlines="30 дней",
            budget=BRIEF_FIELDS["brief_budget"],
        ),
        db_path=db_path,
    )

    at = _new_app()
    # Единица измерения не присваивается автоматически.
    assert at.number_input(key="brief_deadline_value").value is None
    assert at.selectbox(key="brief_deadline_unit").value is None
    assert any("единицы измерения" in value for value in _captions(at))

    # При повторном сохранении без указания единицы значение не переписывается
    # в неверное каноническое представление.
    _click_label(at, "Сохранить бриф")
    assert any("не сохранён" in err.value.lower() for err in at.error)
    saved = brief_repository.get_latest_brief(db_path=db_path)
    assert saved is not None
    assert saved.deadlines == "30 дней"

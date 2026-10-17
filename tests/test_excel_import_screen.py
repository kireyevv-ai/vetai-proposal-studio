"""Тесты UI импорта прайса из Excel на экране «Настройки» (REQ-47).

Проверяют согласованный сценарий: выбор файла → предпросмотр без изменения
базы → режим импорта → подтверждение → сохранение одной транзакцией → результат.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from vetai.db import init_database
from vetai.repositories import price_repository

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

EXISTING = "Аудит текущих процессов"
EXISTING_PRICE = 50000
NEW_SERVICE = "Внедрение решения"
NEW_PRICE_KOPEKS = 150000

MODE_ADD_LABEL = "Только новые услуги"
MODE_UPDATE_LABEL = "Новые и обновить существующие цены"

_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Прайс"
    sheet.append(["Название услуги", "Цена"])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _upload(at: AppTest, data: bytes, name: str = "price.xlsx") -> AppTest:
    at.file_uploader(key="price_import_file_0").set_value(
        (name, data, _XLSX_MIME)
    )
    return at.run()


def _click(at: AppTest, key: str) -> AppTest:
    next(button for button in at.button if button.key == key).click()
    return at.run()


def _prices(db_path: Path) -> dict[str, int]:
    return {
        item.name: item.price_kopeks
        for item in price_repository.list_price_items(db_path=db_path)
    }


def _summary(at: AppTest) -> str:
    """Текст сводки предпросмотра (st.write попадает в markdown)."""
    parts: list[str] = []
    for collection in (
        at.markdown, at.text, at.caption, at.subheader,
        at.info, at.warning, at.error, at.success,
    ):
        for block in collection:
            parts.append(str(block.value))
    return "\n".join(parts)


@pytest.fixture
def db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "import_ui.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(path))
    init_database(path)
    price_repository.add_price_item(EXISTING, EXISTING_PRICE, db_path=path)
    return path


@pytest.fixture
def app(db_path: Path) -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.radio[0].set_value("Настройки")
    at.run()
    assert not at.exception
    return at


# --- Отображение секции ------------------------------------------------------


def test_import_section_is_rendered(app: AppTest) -> None:
    labels = [radio.label for radio in app.radio]
    assert "Режим импорта" in labels
    uploader = app.file_uploader(key="price_import_file_0")
    assert uploader.label == "Файл прайса (.xlsx)"
    assert list(uploader.allowed_type) == [".xlsx"]


def test_sample_download_is_offered(app: AppTest) -> None:
    sample = next(
        button
        for button in app.download_button
        if button.key == "price_import_sample"
    )
    assert sample.label == "Скачать пустой образец Excel"


# --- Предпросмотр без изменения базы ----------------------------------------


def test_preview_shows_counts_without_changing_db(app: AppTest, db_path: Path) -> None:
    app.radio(key="price_import_mode").set_value(MODE_UPDATE_LABEL)
    app.run()
    data = _xlsx([[NEW_SERVICE, 1500], [EXISTING, 750]])
    _upload(app, data)

    assert "Новых: 1" in _summary(app)
    assert "Обновлений: 1" in _summary(app)
    assert "Ошибок: 0" in _summary(app)
    # предпросмотр отмечает обновление цены и называет будущее значение
    assert "Обновление цены" in _table(app, "Действие")
    assert any("750 руб." in str(value) for value in _table(app, "Цена"))

    # база ещё не изменена: предпросмотр ничего не пишет
    assert _prices(db_path) == {EXISTING: EXISTING_PRICE}


def _table(at: AppTest, column: str) -> list[str]:
    """Значения одной колонки предпросмотра (на экране один st.dataframe).

    AppTest не сохраняет ``key`` виджета данных, поэтому берём единственный
    dataframe — других на экране «Настройки» нет.
    """
    frame = at.dataframe[0].value
    return [str(value) for value in frame[column]]


def test_preview_add_only_mode_skips_existing(app: AppTest, db_path: Path) -> None:
    app.radio(key="price_import_mode").set_value(MODE_ADD_LABEL)
    app.run()
    data = _xlsx([[EXISTING, 99999], [NEW_SERVICE, 1500]])
    _upload(app, data)

    assert "Новых: 1" in _summary(app)
    assert "Обновлений: 0" in _summary(app)
    assert "Пропущено: 1" in _summary(app)
    assert _prices(db_path) == {EXISTING: EXISTING_PRICE}


# --- Подтверждение и сохранение ----------------------------------------------


def test_confirm_adds_new_service(app: AppTest, db_path: Path) -> None:
    _upload(app, _xlsx([[NEW_SERVICE, 1500]]))
    _click(app, "price_import_confirm")

    assert any("Импорт выполнен" in msg.value for msg in app.success)
    assert any("добавлено 1" in msg.value for msg in app.success)
    assert _prices(db_path) == {
        EXISTING: EXISTING_PRICE,
        NEW_SERVICE: NEW_PRICE_KOPEKS,
    }


def test_confirm_updates_existing_price_in_update_mode(app: AppTest, db_path: Path) -> None:
    app.radio(key="price_import_mode").set_value(MODE_UPDATE_LABEL)
    app.run()
    _upload(app, _xlsx([[EXISTING, 750]]))

    _click(app, "price_import_confirm")

    assert any("обновлено 1" in msg.value for msg in app.success)
    assert _prices(db_path)[EXISTING] == 75000


def test_confirm_does_not_update_in_add_only_mode(app: AppTest, db_path: Path) -> None:
    app.radio(key="price_import_mode").set_value(MODE_ADD_LABEL)
    app.run()
    _upload(app, _xlsx([[EXISTING, 99999]]))

    # нет строк для импорта → кнопка подтверждения не предлагается
    assert not any(
        button.key == "price_import_confirm" for button in app.button
    )
    assert any("Нет строк для импорта" in info.value for info in app.info)
    assert _prices(db_path) == {EXISTING: EXISTING_PRICE}


def test_uploader_is_reset_after_successful_import(app: AppTest) -> None:
    _upload(app, _xlsx([[NEW_SERVICE, 1500]]))
    _click(app, "price_import_confirm")

    # после импорта файл очищен (новый nonce), результат показан
    assert any("Импорт выполнен" in msg.value for msg in app.success)
    assert app.file_uploader(key="price_import_file_1").value is None
    # и новый файл можно загрузить тем же сценарием
    _upload_again(app, _xlsx([[EXISTING, 750]]))
    assert "Обновлений: 0" in _summary(app)


def _upload_again(at: AppTest, data: bytes) -> AppTest:
    """Загрузить файл после сброса загрузчика (nonce = 1)."""
    at.file_uploader(key="price_import_file_1").set_value(
        ("price2.xlsx", data, _XLSX_MIME)
    )
    return at.run()


# --- Ошибки и предупреждения -------------------------------------------------


def test_invalid_rows_are_reported_and_skipped(app: AppTest, db_path: Path) -> None:
    data = _xlsx(
        [
            ["", 1000],           # пустое название
            ["Без цены", None],   # пустая цена
            ["Отрицательная", -5],
            [NEW_SERVICE, 1000],  # валидная
        ]
    )
    _upload(app, data)

    assert "Ошибок: 3" in _summary(app)
    assert any("Строк с ошибками: 3" in warning.value for warning in app.warning)
    assert any("Пустое название" in err.value for err in app.error)
    assert any("Не указана цена" in err.value for err in app.error)

    _click(app, "price_import_confirm")
    # валидная строка записана, ошибки пропущены
    assert _prices(db_path)[NEW_SERVICE] == 100000


def test_duplicate_in_file_is_visible(app: AppTest) -> None:
    data = _xlsx(
        [
            [NEW_SERVICE, 1000],
            [NEW_SERVICE, 2000],
        ]
    )
    _upload(app, data)
    assert "Ошибок: 1" in _summary(app)
    assert any("Дубликат" in err.value for err in app.error)


def test_archived_match_warns_and_skips(app: AppTest, db_path: Path) -> None:
    archived_id = price_repository.add_price_item(
        "Сопровождение", 90000, db_path=db_path
    )
    price_repository.set_archived(archived_id, True, db_path=db_path)

    _upload(app, _xlsx([["Сопровождение", 5000]]))

    assert any("архиве" in warning.value for warning in app.warning)
    assert "Пропущено: 1" in _summary(app)
    assert not any(
        button.key == "price_import_confirm" for button in app.button
    )
    items = {
        item.name: item
        for item in price_repository.list_price_items(
            db_path=db_path, include_archived=True
        )
    }
    assert items["Сопровождение"].is_active is False
    assert items["Сопровождение"].price_kopeks == 90000


def test_missing_columns_is_fatal_and_db_unchanged(app: AppTest, db_path: Path) -> None:
    workbook = Workbook()
    workbook.active.append(["Сервис", "Стоимость"])
    workbook.active.append(["Услуга", 100])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()

    _upload(app, buffer.getvalue())

    assert any("колонок" in err.value for err in app.error)
    assert "Прочитано строк" not in _summary(app)
    assert _prices(db_path) == {EXISTING: EXISTING_PRICE}


def test_non_xlsx_file_is_blocked_before_our_code(app: AppTest, db_path: Path) -> None:
    """Слой защиты: сам Streamlit не пропускает не-.xlsx в ``st.file_uploader``."""
    app.file_uploader(key="price_import_file_0").set_value(
        ("price.csv", b"a,b", "text/csv")
    )
    app.run()

    # Streamlit отклоняет расширение на уровне виджета — наш сервис не вызывается
    assert app.exception
    assert "Прочитано строк" not in _summary(app)
    assert _prices(db_path) == {EXISTING: EXISTING_PRICE}

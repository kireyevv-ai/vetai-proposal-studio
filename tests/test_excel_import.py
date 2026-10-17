"""Импорт прайса из Excel (.xlsx) — REQ-47.

Сценарии:

- A. Образец: пустой .xlsx только с обязательными заголовками.
- B. Корректный импорт: добавление новых и обновление существующих цен.
- C. Режим «только новые» не меняет цены существующих услуг.
- D. Дубликаты внутри файла не «уходят» молча.
- E. Некорректные цены и пустые строки — ошибки, база не изменяется.
- F. Кириллица: сопоставление названий регистронезависимое.
- G. Защита исторической стоимости КП: снимок и PDF сохранённого КП не меняются.
- H. Повторный импорт того же файла не дублирует и не меняет данные.
- I. Откат транзакции: при ошибке в середине импорта не остаётся частичных данных.
- J. Архивная политика: совпадение с архивной услугой пропускается, архив не
   реактивируется автоматически; услуги из файла не удаляются.
- K. Файловые ограничения: расширение, макросы, обязательные колонки, размер.
- L. Деньги: Decimal, без float; избыточная точность отклоняется.

Тесты работают на отдельной временной БД (``VETAI_DB_PATH``) и не затрагивают
пользовательскую базу.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from vetai.db import connect, init_database
from vetai.models import Brief
from vetai.repositories import brief_repository, price_repository, proposal_repository
from vetai.services import commercial, excel_import, pdf
from vetai.services.excel_import import (
    ACTION_ADD,
    ACTION_ERROR,
    ACTION_SKIP,
    ACTION_UPDATE,
    MAX_FILE_BYTES,
    MODE_ADD,
    MODE_ADD_UPDATE,
    STATUS_SKIP_ARCHIVED,
)
from vetai.validation import format_price

EXISTING = "Аудит текущих процессов"
EXISTING_PRICE = 50000  # копейки = 500 руб.
NEW_SERVICE = "Внедрение решения"
NEW_PRICE = 150000  # 1 500 руб.


# --- Вспомогательные функции -------------------------------------------------


def _xlsx(rows: list[list[object]]) -> bytes:
    """Собрать .xlsx с обязательными заголовками и переданными строками."""
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


def _actions(preview) -> list[str]:
    return [row.action for row in preview.rows]


@pytest.fixture
def db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "import.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(path))
    init_database(path)
    price_repository.add_price_item(EXISTING, EXISTING_PRICE, db_path=path)
    return path


def _price_map(db_path: Path) -> dict[str, int]:
    return {
        item.name: item.price_kopeks
        for item in price_repository.list_price_items(db_path=db_path)
    }


def _seed_stored_proposal(db_path: Path) -> int:
    """Сохранить КП с коммерческим снимком (как в test_deadline_unit_fix)."""
    import json
    from datetime import datetime, timezone

    brief_id = brief_repository.save_brief(
        Brief(
            client="ООО «Исторический клиент»",
            task="Внедрить решение",
            services=[EXISTING],
            deadlines="30 календарных дней",
            budget="100 000 руб.",
        ),
        db_path=db_path,
    )
    now = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "currency": "RUB",
        "items": [{"name": EXISTING, "price_kopeks": EXISTING_PRICE}],
        "total_kopeks": EXISTING_PRICE,
        "missing": [],
        "deadlines": "30 календарных дней",
    }
    body = {
        "provider": "mock",
        "sections": [
            {
                "key": "pricing",
                "title": "Стоимость",
                "text": commercial.expected_sections(snapshot)["pricing"],
                "source": "code",
            }
        ],
        "warnings": [],
        "validation": {"issues": []},
    }
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO proposals (brief_id, current_version, created_at, updated_at) "
            "VALUES (?, 1, ?, ?)",
            (brief_id, now, now),
        )
        proposal_id = int(conn.execute("SELECT id FROM proposals").fetchone()["id"])
        conn.execute(
            "INSERT INTO proposal_versions "
            "(proposal_id, version, status, body, commercial_snapshot, created_at) "
            "VALUES (?, 1, 'generated', ?, ?, ?)",
            (
                proposal_id,
                json.dumps(body, ensure_ascii=False),
                json.dumps(snapshot, ensure_ascii=False),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return proposal_id


# --- A. Образец --------------------------------------------------------------


def test_sample_xlsx_has_only_required_headers(db_path: Path) -> None:
    data = excel_import.build_sample_xlsx()
    assert data[:2] == b"PK"  # это ZIP-контейнер .xlsx

    preview = excel_import.build_preview(
        data, MODE_ADD, db_path=db_path, file_name="obrazec.xlsx"
    )
    assert preview.rows == []
    assert preview.actionable_count == 0
    assert not preview.has_errors


# --- B. Корректный импорт ----------------------------------------------------


def test_import_adds_new_and_updates_existing(db_path: Path) -> None:
    data = _xlsx(
        [
            [NEW_SERVICE, 1500],          # 1500 руб. (int)
            [EXISTING, 750.50],           # обновление: 750,50 руб. (float)
        ]
    )
    preview = excel_import.build_preview(data, MODE_ADD_UPDATE, db_path=db_path)
    assert _actions(preview) == [ACTION_ADD, ACTION_UPDATE]
    assert preview.new_count == 1
    assert preview.update_count == 1
    assert preview.error_count == 0

    result = excel_import.apply_import(preview, db_path=db_path)
    assert (result.added, result.updated) == (1, 1)
    assert _price_map(db_path) == {
        EXISTING: 75050,
        NEW_SERVICE: NEW_PRICE,
    }


def test_money_is_integer_kopeks_not_float(db_path: Path) -> None:
    data = _xlsx([[NEW_SERVICE, 1500.50]])
    preview = excel_import.build_preview(data, MODE_ADD, db_path=db_path)

    row = preview.rows[0]
    assert isinstance(row.price_kopeks, int)
    assert row.price_kopeks == 150050
    assert row.price_display == format_price(150050)


# --- C. Режим «только новые» -------------------------------------------------


def test_add_only_mode_never_touches_existing_prices(db_path: Path) -> None:
    data = _xlsx(
        [
            [EXISTING, 99999],   # должно быть пропущено
            [NEW_SERVICE, 1000],  # должно быть добавлено
        ]
    )
    preview = excel_import.build_preview(data, MODE_ADD, db_path=db_path)

    assert preview.rows[0].action == ACTION_SKIP
    assert preview.rows[1].action == ACTION_ADD
    assert preview.new_count == 1
    assert preview.update_count == 0

    result = excel_import.apply_import(preview, db_path=db_path)
    assert (result.added, result.updated) == (1, 0)
    assert _price_map(db_path)[EXISTING] == EXISTING_PRICE  # цена не изменилась


# --- D. Дубликаты внутри файла ----------------------------------------------


def test_duplicate_names_in_file_are_reported_not_merged(db_path: Path) -> None:
    data = _xlsx(
        [
            [NEW_SERVICE, 1000],
            [NEW_SERVICE, 2000],  # дубликат
        ]
    )
    preview = excel_import.build_preview(data, MODE_ADD, db_path=db_path)

    assert preview.rows[0].action == ACTION_ADD
    assert preview.rows[1].action == ACTION_ERROR
    assert "Дубликат" in preview.rows[1].message
    assert preview.new_count == 1

    result = excel_import.apply_import(preview, db_path=db_path)
    assert (result.added, result.updated) == (1, 0)
    # записан только первый вхождение — цена из первой строки
    assert _price_map(db_path)[NEW_SERVICE] == 100000


def test_duplicate_within_file_is_case_and_whitespace_insensitive(
    db_path: Path,
) -> None:
    data = _xlsx(
        [
            [NEW_SERVICE, 1000],
            ["  внедрение   РЕШЕНИЯ ", 2000],  # тот же сервис, иначе набран
        ]
    )
    preview = excel_import.build_preview(data, MODE_ADD, db_path=db_path)
    assert preview.rows[1].action == ACTION_ERROR
    assert "Дубликат" in preview.rows[1].message


# --- E. Некорректные цены и пустые строки -----------------------------------


def test_invalid_prices_and_empty_rows_are_errors(db_path: Path) -> None:
    data = _xlsx(
        [
            ["", 1000],              # пустое название
            ["Без цены", None],      # пустая цена
            ["Отрицательная", -100], # отрицательная
            ["Текст", "сто рублей"], # нечисловая
            [NEW_SERVICE, 1000],     # валидная строка
        ]
    )
    preview = excel_import.build_preview(data, MODE_ADD, db_path=db_path)

    assert [row.action for row in preview.rows[:4]] == [
        ACTION_ERROR, ACTION_ERROR, ACTION_ERROR, ACTION_ERROR,
    ]
    assert "Пустое название" in preview.rows[0].message
    assert "Не указана цена" in preview.rows[1].message
    assert "отрицательной" in preview.rows[2].message
    assert "числом" in preview.rows[3].message
    assert preview.error_count == 4
    assert preview.new_count == 1

    result = excel_import.apply_import(preview, db_path=db_path)
    assert result.added == 1
    # валидная строка записана, ошибки — нет
    assert _price_map(db_path)[NEW_SERVICE] == 100000


def test_completely_empty_rows_are_skipped_not_errors(db_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Прайс"
    sheet.append(["Название услуги", "Цена"])
    sheet.append([None, None])       # полностью пустая — пропускается
    sheet.append(["", ""])           # пустые строки — пропускается
    sheet.append([NEW_SERVICE, 1000])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()

    preview = excel_import.build_preview(buffer.getvalue(), MODE_ADD, db_path=db_path)
    assert len(preview.rows) == 1
    assert preview.error_count == 0
    assert preview.new_count == 1


def test_float_price_with_three_decimals_is_rejected(db_path: Path) -> None:
    data = _xlsx([[NEW_SERVICE, 1000.123]])
    preview = excel_import.build_preview(data, MODE_ADD, db_path=db_path)

    assert preview.rows[0].action == ACTION_ERROR
    assert "двух знаков" in preview.rows[0].message
    assert preview.actionable_count == 0


# --- F. Кириллица и регистр --------------------------------------------------


def test_cyrillic_names_match_case_insensitively(db_path: Path) -> None:
    data = _xlsx([["аудит текущих процессов", 99999]])  # строчными
    preview = excel_import.build_preview(data, MODE_ADD_UPDATE, db_path=db_path)

    row = preview.rows[0]
    assert row.action == ACTION_UPDATE
    assert row.match_id == price_repository.list_price_items(db_path=db_path)[0].id

    excel_import.apply_import(preview, db_path=db_path)
    assert _price_map(db_path)[EXISTING] == 9999900


# --- G. Защита исторической стоимости КП -------------------------------------


def test_import_does_not_change_stored_proposal_cost_or_pdf(db_path: Path) -> None:
    from test_versioning_export import pdf_text

    proposal_id = _seed_stored_proposal(db_path)
    version_id = proposal_repository.list_versions(proposal_id, db_path=db_path)[0][
        "id"
    ]
    draft_before = proposal_repository.get_version(version_id, db_path=db_path)
    pdf_before = pdf_text(pdf.build_pdf(draft_before, client="ООО «Исторический клиент»"))
    snapshot_before = dict(draft_before.commercial_snapshot)

    data = _xlsx([[EXISTING, 2000]])  # поднимаем цену в прайсе до 2000 руб.
    preview = excel_import.build_preview(data, MODE_ADD_UPDATE, db_path=db_path)
    assert preview.rows[0].action == ACTION_UPDATE
    excel_import.apply_import(preview, db_path=db_path)

    # прайс обновился...
    assert _price_map(db_path)[EXISTING] == 200000

    # ...а сохранённый КП не изменился
    draft_after = proposal_repository.get_version(version_id, db_path=db_path)
    assert draft_after.commercial_snapshot == snapshot_before
    assert draft_after.commercial_snapshot["total_kopeks"] == EXISTING_PRICE
    assert draft_after.commercial_snapshot["items"][0]["price_kopeks"] == EXISTING_PRICE

    # текст PDF (включая стоимость 500 руб.) остался прежним
    pdf_after = pdf_text(pdf.build_pdf(draft_after, client="ООО «Исторический клиент»"))
    assert pdf_after == pdf_before
    assert "500 руб." in pdf_after
    assert "2 000 руб." not in pdf_after


# --- H. Повторный импорт -----------------------------------------------------


def test_reimport_same_file_in_add_update_is_stable(db_path: Path) -> None:
    data = _xlsx([[EXISTING, 750], [NEW_SERVICE, 1000]])

    first = excel_import.build_preview(data, MODE_ADD_UPDATE, db_path=db_path)
    assert (first.new_count, first.update_count) == (1, 1)
    excel_import.apply_import(first, db_path=db_path)
    prices_after_first = _price_map(db_path)

    # тот же файл повторно: ничего не добавляется и не обновляется
    second = excel_import.build_preview(data, MODE_ADD_UPDATE, db_path=db_path)
    assert second.new_count == 0
    assert second.update_count == 0
    assert second.has_errors is False

    result = excel_import.apply_import(second, db_path=db_path)
    assert (result.added, result.updated) == (0, 0)
    assert _price_map(db_path) == prices_after_first


def test_reimport_same_file_in_add_only_skips_everything(db_path: Path) -> None:
    data = _xlsx([[EXISTING, 750], [NEW_SERVICE, 1000]])
    excel_import.apply_import(
        excel_import.build_preview(data, MODE_ADD_UPDATE, db_path=db_path),
        db_path=db_path,
    )

    preview = excel_import.build_preview(data, MODE_ADD, db_path=db_path)
    assert preview.new_count == 0
    assert preview.actionable_count == 0
    assert all(row.action == ACTION_SKIP for row in preview.rows)


# --- I. Откат транзакции (нет частичного импорта) ----------------------------


def test_repository_rolls_back_on_conflicting_adds(db_path: Path) -> None:
    with pytest.raises(ValueError):
        price_repository.apply_price_import(
            [("Дубль", 1000), ("Дубль", 2000)], [], db_path=db_path
        )

    # первая вставка откатилась вместе со второй
    assert "Дубль" not in _price_map(db_path)


def test_repository_rolls_back_adds_when_update_fails(db_path: Path) -> None:
    existing_id = price_repository.list_price_items(db_path=db_path)[0].id

    with pytest.raises(ValueError):
        price_repository.apply_price_import(
            [(NEW_SERVICE, 1000)],
            [(existing_id + 999, 5000)],  # несуществующая позиция
            db_path=db_path,
        )

    prices = _price_map(db_path)
    assert NEW_SERVICE not in prices          # добавление откатилось
    assert prices[EXISTING] == EXISTING_PRICE  # цена не изменилась


def test_apply_import_propagates_and_keeps_db_unchanged(db_path: Path) -> None:
    """Конфликт внутри одной транзакции: база остаётся без частичных данных."""
    from vetai.services.excel_import import ImportPreview, ImportRow

    duplicate = ImportRow(
        row_number=1, name=NEW_SERVICE, price_kopeks=100000,
        price_display="1 000 руб.", action=ACTION_ADD, status="Новая услуга",
    )
    preview = ImportPreview(mode=MODE_ADD, rows=[duplicate, duplicate])
    preview.new_count = 2

    with pytest.raises(ValueError):
        excel_import.apply_import(preview, db_path=db_path)

    assert _price_map(db_path) == {EXISTING: EXISTING_PRICE}


def test_invalid_price_rejected_by_repository(db_path: Path) -> None:
    with pytest.raises(ValueError):
        price_repository.apply_price_import([(NEW_SERVICE, -1)], [], db_path=db_path)
    with pytest.raises(ValueError):
        price_repository.apply_price_import([(NEW_SERVICE, 1000.5)], [], db_path=db_path)
    assert _price_map(db_path) == {EXISTING: EXISTING_PRICE}


# --- J. Архивная политика и защита данных -----------------------------------


def test_archived_match_is_skipped_and_not_reactivated(db_path: Path) -> None:
    archived_name = "Сопровождение"
    archived_id = price_repository.add_price_item(
        archived_name, 90000, db_path=db_path
    )
    price_repository.set_archived(archived_id, True, db_path=db_path)

    data = _xlsx([[archived_name, 5000], [NEW_SERVICE, 1000]])
    preview = excel_import.build_preview(data, MODE_ADD_UPDATE, db_path=db_path)

    archived_row, new_row = preview.rows
    assert archived_row.action == ACTION_SKIP
    assert archived_row.status == STATUS_SKIP_ARCHIVED
    assert "архив" in archived_row.message.lower()
    assert "архиве" in " ".join(preview.warnings).lower()
    assert new_row.action == ACTION_ADD

    excel_import.apply_import(preview, db_path=db_path)

    items = {
        item.name: item
        for item in price_repository.list_price_items(
            db_path=db_path, include_archived=True
        )
    }
    # архивная услуга не реактивировалась и её цена не изменилась
    assert items[archived_name].is_active is False
    assert items[archived_name].price_kopeks == 90000
    # новая услуга добавлена
    assert items[NEW_SERVICE].is_active is True


def test_import_never_deletes_services_missing_from_file(db_path: Path) -> None:
    data = _xlsx([[NEW_SERVICE, 1000]])  # в файле только новая услуга
    preview = excel_import.build_preview(data, MODE_ADD_UPDATE, db_path=db_path)
    excel_import.apply_import(preview, db_path=db_path)

    names = set(_price_map(db_path))
    assert names == {EXISTING, NEW_SERVICE}  # существующая не удалена


def test_import_does_not_touch_briefs_or_proposals(db_path: Path) -> None:
    _seed_stored_proposal(db_path)
    proposals_before = proposal_repository.list_proposals(db_path=db_path)
    briefs_before = len(proposals_before)

    data = _xlsx([[EXISTING, 100]])
    excel_import.apply_import(
        excel_import.build_preview(data, MODE_ADD_UPDATE, db_path=db_path),
        db_path=db_path,
    )

    assert len(proposal_repository.list_proposals(db_path=db_path)) == briefs_before
    assert proposal_repository.get_latest_draft(db_path=db_path) is not None


# --- K. Файловые ограничения -------------------------------------------------


def test_missing_required_columns_is_fatal(db_path: Path) -> None:
    workbook = Workbook()
    workbook.active.append(["Сервис", "Стоимость"])
    workbook.active.append(["Услуга", 100])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()

    with pytest.raises(ValueError, match="колонок"):
        excel_import.build_preview(buffer.getvalue(), MODE_ADD, db_path=db_path)


def test_macro_bearing_file_is_rejected(db_path: Path) -> None:
    """Файл с макросами (VBA) отклоняется, а не «тихо» выполняется."""
    import zipfile

    buffer = io.BytesIO(_xlsx([[NEW_SERVICE, 1000]]))
    with zipfile.ZipFile(buffer, "a") as archive:
        archive.writestr("xl/vbaProject.bin", b"\x00\x01\x02")
    data_with_macro = buffer.getvalue()

    with pytest.raises(ValueError, match="макрос"):
        excel_import.build_preview(data_with_macro, MODE_ADD, db_path=db_path)


def test_corrupt_or_non_zip_file_is_rejected(db_path: Path) -> None:
    with pytest.raises(ValueError):
        excel_import.build_preview(b"this is not an xlsx", MODE_ADD, db_path=db_path)


def test_oversized_file_is_rejected(db_path: Path) -> None:
    with pytest.raises(ValueError, match="большой"):
        excel_import.build_preview(b"\x00" * (MAX_FILE_BYTES + 1), MODE_ADD, db_path=db_path)


def test_invalid_extension_is_rejected_by_name_check() -> None:
    with pytest.raises(ValueError, match=".xlsx"):
        excel_import._check_extension("price.xlsm")
    with pytest.raises(ValueError, match=".xlsx"):
        excel_import._check_extension("price.csv")
    excel_import._check_extension("price.xlsx")  # допустимое расширение


def test_unknown_mode_is_rejected(db_path: Path) -> None:
    data = _xlsx([[NEW_SERVICE, 1000]])
    with pytest.raises(ValueError, match="режим"):
        excel_import.build_preview(data, "replace_everything", db_path=db_path)


# --- L. Точность денег через Decimal ----------------------------------------


def test_decimal_branch_and_excessive_precision() -> None:
    from decimal import Decimal

    assert excel_import.price_to_kopeks(Decimal("1500.50")) == 150050
    assert excel_import.price_to_kopeks(Decimal("1500.5")) == 150050
    with pytest.raises(ValueError, match="двух знаков"):
        excel_import.price_to_kopeks(Decimal("1500.505"))

    # Excel хранит числа как double — 0.1 + 0.2 даёт 0.30000000000000004;
    # через Decimal(repr(...)) мы копейки считаем точно.
    assert excel_import.price_to_kopeks(0.1 + 0.2) == 30


def test_bool_and_unsupported_types_are_rejected() -> None:
    with pytest.raises(ValueError):
        excel_import.price_to_kopeks(True)
    with pytest.raises(ValueError):
        excel_import.price_to_kopeks(object())


def test_price_string_form_is_supported(db_path: Path) -> None:
    data = _xlsx([[NEW_SERVICE, "1 500,50"]])
    preview = excel_import.build_preview(data, MODE_ADD, db_path=db_path)
    assert preview.rows[0].price_kopeks == 150050


def test_normalize_name_collapses_whitespace_and_case() -> None:
    assert excel_import.normalize_name("  Аудит   текущих\nпроцессов ") == (
        "аудит текущих процессов"
    )
    assert excel_import.normalize_name("Щука") == excel_import.normalize_name("щука")

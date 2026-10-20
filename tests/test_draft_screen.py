"""Тесты экрана «Черновик» и сценария «бриф → черновик» (REQ-06, REQ-15, REQ-36).

Провайдер — mock (AI_PROVIDER=mock): реальный API не вызывается.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from vetai.db import init_database
from vetai.repositories import brief_repository, price_repository

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

PRICES = [("Аудит текущих процессов", 50000), ("Внедрение решения", 120000)]


def _new_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppTest:
    db = tmp_path / "draft_test.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(db))
    init_database(db)
    for name, kopeks in PRICES:
        price_repository.add_price_item(name, kopeks, db_path=db)
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    return at


def _fill_valid_brief(app: AppTest) -> None:
    app.text_input(key="brief_client").set_value("ООО «Учебный клиент»")
    app.text_area(key="brief_task").set_value("Внедрить решение")
    app.multiselect(key="brief_services").set_value([PRICES[0][0]])
    app.number_input(key="brief_deadline_value").set_value(30)
    app.selectbox(key="brief_deadline_unit").select("календарные дни")
    app.text_input(key="brief_budget").set_value("100 000 руб.")
    app.run()


def test_draft_screen_without_draft_shows_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _new_app(monkeypatch, tmp_path)
    app.radio[0].set_value("Черновик")
    app.run()

    assert not app.exception
    assert any("не сгенерирован" in info.value.lower() for info in app.info)


def test_generate_creates_draft_and_opens_draft_screen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    app = _new_app(monkeypatch, tmp_path)
    _fill_valid_brief(app)

    assert app.button[1].label == "Сгенерировать КП"
    app.button[1].click().run()

    assert not app.exception
    assert app.radio[0].value == "Черновик"
    assert any("подготовлено" in msg.value.lower() for msg in app.success)
    subheaders = [block.value for block in app.subheader]
    assert any("Стоимость" in title for title in subheaders)
    assert any("Сроки" in title for title in subheaders)
    # Разделы нумеруются как визуальное оформление макета («01. …»).
    assert any("01. " in title for title in subheaders)


def test_generation_shows_pricing_from_price_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    app = _new_app(monkeypatch, tmp_path)
    _fill_valid_brief(app)
    app.button[1].click().run()

    assert not app.exception
    rendered = "\n".join(block.value for block in app.markdown) + "\n".join(
        block.value for block in app.text
    )
    assert "500 руб." in rendered


def test_draft_marks_sections_without_trusted_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Разделы без доверенных данных не генерируются и помечаются (Часть А, п. 6)."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    app = _new_app(monkeypatch, tmp_path)
    _fill_valid_brief(app)
    app.button[1].click().run()

    assert not app.exception
    # Техническая заглушка не показывается как обычный текст.
    rendered = "\n".join(block.value for block in app.markdown) + "\n".join(
        block.value for block in app.text
    )
    assert "ручная доработка" not in rendered
    assert "раздел не сформирован моделью" not in rendered.lower()
    # Разделы «О компании» и «Прочие условия» помечены как требующие уточнения
    # (некритические замечания собраны в блоке «Рекомендации по улучшению»).
    rendered_all = rendered + "\n" + "\n".join(info.value for info in app.info)
    assert rendered_all.lower().count("требует уточнения") >= 2


def test_draft_screen_shows_document_without_info_panel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Рабочая область — широкий редактор без правой панели; рекомендации —
    в одном сворачиваемом блоке под редактором (без дублей)."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    app = _new_app(monkeypatch, tmp_path)
    _fill_valid_brief(app)
    app.button[1].click().run()

    assert not app.exception
    markdown_text = "\n".join(block.value for block in app.markdown)
    captions = "\n".join(block.value for block in app.caption)

    assert "РЕДАКТОР КП" in markdown_text
    assert "Коммерческое предложение" in markdown_text
    # Правая информационная панель удалена.
    assert "О документе" not in markdown_text
    assert "Проверка документа" not in markdown_text
    assert "Коммерческие условия" not in markdown_text
    # Клиент, версия и дата показаны компактно под заголовком.
    assert "Учебный клиент" in captions
    assert "Версия: 1" in captions
    assert "Сохранено:" in captions

    assert "Рекомендации по улучшению" in [exp.label for exp in app.expander]
    # Все уникальные замечания доступны в рекомендациях — без дублей.
    assert (
        markdown_text.count(
            "Раздел «О компании» не заполнен — требует уточнения."
        )
        == 1
    )
    assert (
        markdown_text.count(
            "Раздел «Прочие условия» не заполнен — требует уточнения."
        )
        == 1
    )


def test_draft_shows_deadline_with_explicit_unit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    app = _new_app(monkeypatch, tmp_path)
    _fill_valid_brief(app)
    app.button[1].click().run()

    rendered = "\n".join(block.value for block in app.markdown) + "\n".join(
        block.value for block in app.text
    )
    assert "30 календарных дней" in rendered


def test_provider_config_error_keeps_brief_saved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "draft_fail.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(db))
    monkeypatch.setenv("AI_PROVIDER", "gigachat")
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "")
    init_database(db)
    for name, kopeks in PRICES:
        price_repository.add_price_item(name, kopeks, db_path=db)
    app = AppTest.from_file(str(APP_PATH), default_timeout=30)
    app.run()
    _fill_valid_brief(app)

    app.button[1].click().run()

    assert not app.exception
    # Остались на экране брифа, показана понятная ошибка.
    assert app.radio[0].value == "Бриф"
    assert any("не создан" in err.value.lower() for err in app.error)
    # Бриф сохранён до обращения к провайдеру (REQ-36).
    assert brief_repository.get_latest_brief(db_path=db) is not None

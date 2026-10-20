"""Блокировка экспорта PDF без подтверждённой стоимости (вариант А).

Услуга без цены в активном прайсе означает, что итоговая стоимость не
рассчитана. Такой КП нельзя скачать PDF, пока цена не исправлена; исправление
цены создаёт новую версию, старые версии и их коммерческие снимки не меняются.

Сценарии:

- A. Снимок с ``missing`` → экспорт заблокирован с понятным сообщением.
- B. Экран «Предпросмотр» без цены не показывает кнопку PDF и объясняет причину.
- C. Клиентский PDF не содержит служебных сообщений («Уточните прайс…»).
- D. Исправление цены создаёт новую версию; старая не меняется, экспорт
  разблокирован только для новой версии.

Тесты работают на отдельной временной БД (``VETAI_DB_PATH``).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from vetai.db import connect, init_database
from vetai.models import Brief
from vetai.repositories import brief_repository, price_repository, proposal_repository
from vetai.services import commercial, export_checks, pdf
from test_versioning_export import pdf_text

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

SERVICE = "Аудит текущих процессов"
PRICE_KOPEKS = 50000
MISSING_SERVICE = "Экспертиза без цены"
CLIENT = "ООО «Учебный клиент»"
DEADLINE = "30 календарных дней"
DEADLINE_TEXT = "30 календарных дней"

SCREEN_DRAFT = "Черновик"
SCREEN_PREVIEW = "Предпросмотр и PDF"


@pytest.fixture
def db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "export_price_block.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(path))
    monkeypatch.setenv("AI_PROVIDER", "mock")
    init_database(path)
    price_repository.add_price_item(SERVICE, PRICE_KOPEKS, db_path=path)
    return path


def _seed_with_missing(db_path: Path) -> tuple[int, int]:
    """Создать бриф и версию КП, где у одной услуги нет цены в прайсе."""
    brief_id = brief_repository.save_brief(
        Brief(
            client=CLIENT,
            task="Внедрить решение",
            services=[SERVICE, MISSING_SERVICE],
            deadlines=DEADLINE,
            budget="100 000 руб.",
        ),
        db_path=db_path,
    )
    now = datetime.now(timezone.utc).isoformat()
    data = commercial.build_commercial_data(
        [SERVICE, MISSING_SERVICE], DEADLINE, db_path=db_path
    )
    snapshot = commercial.build_snapshot(data, DEADLINE)
    expected = commercial.expected_sections(snapshot)
    body = {
        "provider": "mock",
        "sections": [
            {"key": "task", "title": "Описание задачи", "text": "Внедрить решение.", "source": "model"},
            {"key": "scope", "title": "Состав работ и услуги", "text": "Работы по внедрению.", "source": "model"},
            {"key": "deadlines", "title": "Сроки", "text": expected["deadlines"], "source": "code"},
            {"key": "pricing", "title": "Стоимость", "text": expected["pricing"], "source": "code"},
        ],
        "warnings": [],
        "validation": {"issues": []},
    }
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO proposals (brief_id, current_version, created_at, updated_at) VALUES (?, 1, ?, ?)",
            (brief_id, now, now),
        )
        proposal_id = int(conn.execute("SELECT id FROM proposals").fetchone()["id"])
        conn.execute(
            "INSERT INTO proposal_versions (proposal_id, version, status, body, commercial_snapshot, created_at) "
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
    return brief_id, proposal_id


def _new_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    return at


def _goto(at: AppTest, screen: str) -> AppTest:
    at.radio[0].set_value(screen)
    return at.run()


def _click(at: AppTest, key: str) -> AppTest:
    next(button for button in at.button if button.key == key).click()
    return at.run()


# --- A: снимок без цены блокирует экспорт ------------------------------------


def test_A_missing_price_blocks_export(db_path: Path) -> None:
    _seed_with_missing(db_path)
    draft = proposal_repository.get_latest_draft(db_path=db_path)

    check = export_checks.check_for_export(draft)
    assert check.can_export is False
    assert any("Не указана стоимость" in c for c in check.critical), check.critical


# --- B: экран предпросмотра без цены не даёт скачать PDF ---------------------


def test_B_preview_without_price_hides_download(db_path: Path) -> None:
    _seed_with_missing(db_path)
    at = _new_app()
    _goto(at, SCREEN_PREVIEW)

    assert not at.exception
    assert not at.download_button, "без подтверждённой цены кнопка PDF недоступна"
    rendered = "\n".join(
        [err.value for err in at.error]
        + [block.value for block in at.markdown]
    )
    assert "Экспорт заблокирован" in rendered
    assert "Не указана стоимость" in rendered


# --- C: клиентский PDF не содержит служебных сообщений -----------------------


def test_C_client_pdf_has_no_service_wording(db_path: Path) -> None:
    _seed_with_missing(db_path)
    draft = proposal_repository.get_latest_draft(db_path=db_path)

    text = pdf_text(pdf.build_pdf(draft, CLIENT))
    assert "Уточните прайс" not in text
    assert "требует уточнения" not in text.lower()


# --- D: исправление цены создаёт новую версию, старая не меняется ------------


def test_D_price_fix_new_version_unblocks_export(db_path: Path) -> None:
    _brief_id, proposal_id = _seed_with_missing(db_path)
    old = proposal_repository.get_version(
        proposal_repository.list_versions(proposal_id, db_path=db_path)[0]["id"],
        db_path=db_path,
    )
    assert old is not None
    old_snapshot = dict(old.commercial_snapshot)

    at = _new_app()
    _goto(at, SCREEN_DRAFT)

    price_repository.add_price_item(MISSING_SERVICE, 25000, db_path=db_path)

    at = _click(at, "editor_refresh_commercial")
    at = _click(at, "editor_save")
    assert not at.exception

    versions = proposal_repository.list_versions(proposal_id, db_path=db_path)
    assert len(versions) == 2, "исправление цены должно создать новую версию"

    unchanged = proposal_repository.get_version(old.version_id, db_path=db_path)
    assert unchanged is not None
    assert unchanged.commercial_snapshot == old_snapshot
    assert export_checks.check_for_export(unchanged).can_export is False

    new = proposal_repository.get_version(versions[-1]["id"], db_path=db_path)
    assert new is not None
    assert export_checks.check_for_export(new).can_export is True

    at = _goto(at, SCREEN_PREVIEW)
    assert at.download_button, "после исправления цены PDF доступен"

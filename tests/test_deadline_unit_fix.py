"""Регрессия: уточнение единицы срока в старых КП (Часть Б, обратная совместимость).

Ранее сохранённые версии КП могли содержать срок только числом (например «30»)
без единицы измерения. Такая версия справедливо блокируется защитной проверкой
перед экспортом. Единица измерения **не назначается автоматически**: пользователь
явно выбирает её, после чего создаётся **новая версия** с полным сроком; старая
версия не изменяется, цена берётся из прежнего коммерческого снимка.

Сценарии:

- A. Старый срок «30» блокирует экспорт (критическое расхождение с доверенными
  данными), но PDF сам по себе собирается — причина именно в старых данных.
- B. Новый КП со сроком и единицей из брифа экспортируется без ошибок.
- C. Подтверждение единицы создаёт новую версию; старая не изменяется.
- D. Новая версия содержит полный срок и проходит проверку перед экспортом.
- E. PDF новой версии содержит подтверждённый срок и совпадает с предпросмотром.
- F. Цена (из коммерческого снимка) не меняется.
- G. Единица не назначается автоматически (нет значения по умолчанию в UI).

Тесты работают на отдельной временной БД (``VETAI_DB_PATH``) и не затрагивают
пользовательскую базу. Провайдер — ``mock`` (реальный API не вызывается).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from vetai.db import connect, init_database
from vetai.deadlines import format_deadline
from vetai.models import Brief
from vetai.repositories import brief_repository, price_repository, proposal_repository
from vetai.services import commercial, deadline_fix, export_checks, pdf
from test_versioning_export import pdf_text

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

SERVICE = "Аудит текущих процессов"
PRICE_KOPEKS = 50000
LEGACY_DEADLINE = "30"
CLIENT = "ООО «Старый клиент»"
FULL_DEADLINE = "30 календарных дней"
UNIT_LABEL = "календарные дни"

SCREEN_BRIEF = "Бриф"
SCREEN_PREVIEW = "Предпросмотр и PDF"


@pytest.fixture
def db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "deadline_fix.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(path))
    monkeypatch.setenv("AI_PROVIDER", "mock")
    init_database(path)
    price_repository.add_price_item(SERVICE, PRICE_KOPEKS, db_path=path)
    return path


# --- Вспомогательные функции -------------------------------------------------


def _seed_legacy(db_path: Path) -> tuple[int, int]:
    """Создать бриф и сохранённую версию КП старого формата (срок «30»)."""
    brief_id = brief_repository.save_brief(
        Brief(
            client=CLIENT,
            task="Внедрить решение",
            services=[SERVICE],
            deadlines=LEGACY_DEADLINE,
            budget="100 000 руб.",
        ),
        db_path=db_path,
    )
    now = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "currency": "RUB",
        "items": [{"name": SERVICE, "price_kopeks": PRICE_KOPEKS}],
        "total_kopeks": PRICE_KOPEKS,
        "missing": [],
        "deadlines": LEGACY_DEADLINE,
    }
    body = {
        "provider": "mock",
        "sections": [
            {"key": "task", "title": "Описание задачи", "text": "Внедрить решение.", "source": "model"},
            {"key": "scope", "title": "Состав работ", "text": "Работы по внедрению.", "source": "model"},
            {"key": "deadlines", "title": "Сроки", "text": LEGACY_DEADLINE, "source": "code"},
            {"key": "pricing", "title": "Стоимость", "text": commercial.expected_sections(snapshot)["pricing"], "source": "code"},
        ],
        "warnings": ["В брифе не указана единица измерения сроков — раздел «Сроки» требует уточнения."],
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
            (proposal_id, json.dumps(body, ensure_ascii=False), json.dumps(snapshot, ensure_ascii=False), now),
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


def _render_text(at: AppTest) -> str:
    parts: list[str] = []
    for collection in (at.markdown, at.text, at.subheader, at.caption, at.info, at.warning, at.error):
        for block in collection:
            parts.append(block.value)
    return "\n".join(parts)


def _section(draft, key: str):
    return next(section for section in draft.sections if section.key == key)


def _versions(db_path: Path, proposal_id: int) -> list[dict]:
    return proposal_repository.list_versions(proposal_id, db_path=db_path)


# --- A: старый срок «30» блокирует экспорт ----------------------------------


def test_A_legacy_deadline_blocks_export_but_pdf_builds(db_path: Path) -> None:
    _seed_legacy(db_path)
    draft = proposal_repository.get_latest_draft(db_path=db_path)

    check = export_checks.check_for_export(draft)
    assert check.can_export is False
    assert any("Сроки" in c for c in check.critical), check.critical

    # Причина — старые данные, а не генерация PDF: PDF собирается напрямую.
    raw = pdf.build_pdf(draft, CLIENT)
    assert raw[:5] == b"%PDF-"
    assert pdf.pdf_page_count(raw) >= 1


# --- B: новый КП со сроком и единицей экспортируется без ошибок --------------


def test_B_new_kp_with_unit_exports_without_errors(db_path: Path) -> None:
    at = _new_app()
    at.text_input(key="brief_client").set_value("ООО «Новый клиент»")
    at.text_area(key="brief_task").set_value("Внедрить решение")
    at.multiselect(key="brief_services").set_value([SERVICE])
    at.number_input(key="brief_deadline_value").set_value(30)
    at.selectbox(key="brief_deadline_unit").select(UNIT_LABEL)
    at.text_input(key="brief_budget").set_value("100 000 руб.")
    at.run()
    next(b for b in at.button if b.label == "Сгенерировать КП").click()
    at.run()
    assert not at.exception

    draft = proposal_repository.get_latest_draft(db_path=db_path)
    assert export_checks.check_for_export(draft).can_export is True

    _goto(at, SCREEN_PREVIEW)
    assert at.download_button, "для корректного КП должна быть доступна кнопка PDF"


# --- C: подтверждение единицы создаёт новую версию, старая не меняется --------


def test_C_confirming_unit_creates_new_version_and_keeps_old(db_path: Path) -> None:
    _brief_id, proposal_id = _seed_legacy(db_path)
    old_id = _versions(db_path, proposal_id)[0]["id"]

    at = _new_app()
    _goto(at, SCREEN_PREVIEW)
    text = _render_text(at)
    assert "без единицы измерения" in text

    at.selectbox(key="deadline_fix_unit").select(UNIT_LABEL)
    at.run()
    next(b for b in at.button if b.key == "deadline_fix_confirm").click()
    at.run()
    assert not at.exception

    versions = _versions(db_path, proposal_id)
    assert [v["version"] for v in versions] == [1, 2]
    assert proposal_repository.get_proposal(proposal_id, db_path=db_path)["current_version"] == 2

    # Старая версия не изменена.
    old = proposal_repository.get_version(old_id, db_path=db_path)
    assert _section(old, "deadlines").text == LEGACY_DEADLINE
    assert old.status == "generated"


# --- D: новая версия содержит полный срок и проходит проверку ---------------


def test_D_new_version_has_full_deadline_and_passes_check(db_path: Path) -> None:
    _brief_id, proposal_id = _seed_legacy(db_path)
    draft = proposal_repository.get_latest_draft(db_path=db_path)

    _new_id, new_version = deadline_fix.create_corrected_version(
        draft, "calendar_days", db_path=db_path
    )
    assert new_version == 2

    corrected = proposal_repository.get_latest_draft(db_path=db_path)
    deadlines_text = _section(corrected, "deadlines").text
    assert FULL_DEADLINE in deadlines_text
    assert "единица измерения не указана" not in deadlines_text
    assert export_checks.check_for_export(corrected).can_export is True


# --- E: PDF новой версии содержит срок и совпадает с предпросмотром ----------


def test_E_new_version_pdf_contains_deadline_and_matches_preview(db_path: Path) -> None:
    _brief_id, proposal_id = _seed_legacy(db_path)

    at = _new_app()
    _goto(at, SCREEN_PREVIEW)
    at.selectbox(key="deadline_fix_unit").select(UNIT_LABEL)
    at.run()
    next(b for b in at.button if b.key == "deadline_fix_confirm").click()
    at.run()
    assert not at.exception

    draft = proposal_repository.get_latest_draft(db_path=db_path)
    assert draft.version == 2
    raw = pdf.build_pdf(draft, CLIENT)
    text = pdf_text(raw)

    assert FULL_DEADLINE in text
    assert FULL_DEADLINE in _render_text(at)
    assert at.download_button, "после уточнения срока PDF должен быть доступен"


# --- F: цена из коммерческого снимка не меняется -----------------------------


def test_F_price_from_snapshot_is_preserved(db_path: Path) -> None:
    _brief_id, proposal_id = _seed_legacy(db_path)
    draft = proposal_repository.get_latest_draft(db_path=db_path)
    pricing_before = _section(draft, "pricing").text
    snapshot_before = dict(draft.commercial_snapshot)

    new_id, _ = deadline_fix.create_corrected_version(draft, "months", db_path=db_path)
    corrected = proposal_repository.get_version(new_id, db_path=db_path)

    assert corrected.commercial_snapshot["items"] == snapshot_before["items"]
    assert corrected.commercial_snapshot["total_kopeks"] == snapshot_before["total_kopeks"]
    assert _section(corrected, "pricing").text == pricing_before
    assert corrected.commercial_snapshot["deadlines"] == format_deadline(30, "months")


# --- G: единица не назначается автоматически ---------------------------------


def test_G_unit_is_not_assigned_automatically(db_path: Path) -> None:
    _seed_legacy(db_path)
    draft = proposal_repository.get_latest_draft(db_path=db_path)

    value, unit = deadline_fix.legacy_deadline(draft)
    assert value == 30
    assert unit is None
    assert deadline_fix.needs_unit(draft) is True

    # В интерфейсе единица не выбрана по умолчанию (нет автоназначения).
    at = _new_app()
    _goto(at, SCREEN_PREVIEW)
    selectbox = next(sb for sb in at.selectbox if sb.key == "deadline_fix_unit")
    assert selectbox.value is None

    # Без выбранной единицы подтверждение невозможно.
    confirm = next(b for b in at.button if b.key == "deadline_fix_confirm")
    assert getattr(confirm, "disabled", False) is True

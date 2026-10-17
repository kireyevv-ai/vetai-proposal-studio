"""Регрессия этапа №5 (ручной редактор, версии, предпросмотр и PDF, история).

Воспроизводит сценарии A–J вокруг дефекта, при котором предпросмотр и PDF
показывали *старую* версию КП: идентификатор выбранной в истории версии
(``preview_version_id``) закреплялся в сессии и не сбрасывался при сохранении
новой версии в редакторе.

Сценарии:

- A. После генерации v1 → правки → сохранения v2 предпросмотр показывает v2.
- B. Открытие предпросмотра старой версии в истории, затем правка и сохранение
  v2 — предпросмотр снова показывает актуальную v2 (ключевая регрессия).
- C. После «перезагрузки» (новая сессия) предпросмотр использует последнюю
  сохранённую версию.
- D. Явно выбранная в истории старая версия показывается с её номером и
  предупреждением; актуальная версия КП не меняется.
- E. Открытие предпросмотра не создаёт новую версию.
- F. Скачивание PDF не создаёт новую версию, но помечает версию ``exported``.
- G. Старые версии не удаляются при сохранении новой.
- H. Коммерческие разделы (цены, сроки) не редактируются и совпадают с
  доверенными данными после правки других разделов.
- I. PDF содержит отредактированный текст и не содержит служебных пометок.
- J. Сохранение без изменений не создаёт новую версию.

Тесты работают на отдельной временной БД (``VETAI_DB_PATH``) и не затрагивают
пользовательскую базу. Провайдер — ``mock`` (реальный API не вызывается).
"""

from __future__ import annotations

import base64
import re
import zlib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from vetai.db import init_database
from vetai.repositories import price_repository, proposal_repository
from vetai.services import pdf

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

SERVICE_A = "Аудит текущих процессов"
SERVICE_B = "Консультация по задаче"
SEED_PRICES: list[tuple[str, int]] = [(SERVICE_A, 50000), (SERVICE_B, 15000)]

BRIEF_CLIENT = "ООО «Учебный клиент»"
BRIEF_TASK = "Внедрить решение"
DEADLINE_VALUE = 30
DEADLINE_UNIT = "календарные дни"

EDITED_TASK = "Уточнённая задача: внедрить решение поэтапно по согласованному плану."
STALE_PIN_USER_TASK = "Правка после просмотра старой версии."

SCREEN_BRIEF = "Бриф"
SCREEN_DRAFT = "Черновик"
SCREEN_PREVIEW = "Предпросмотр и PDF"
SCREEN_HISTORY = "История КП"


@pytest.fixture
def db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "versioning_export.db"
    monkeypatch.setenv("VETAI_DB_PATH", str(path))
    monkeypatch.setenv("AI_PROVIDER", "mock")
    init_database(path)
    for name, kopeks in SEED_PRICES:
        price_repository.add_price_item(name, kopeks, db_path=path)
    return path


# --- Вспомогательные функции -------------------------------------------------


def _new_app() -> AppTest:
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


def _render_text(at: AppTest) -> str:
    """Собрать весь видимый текст экрана (markdown/text/subheader/caption/info)."""
    parts: list[str] = []
    for block in at.markdown:
        parts.append(block.value)
    for block in at.text:
        parts.append(block.value)
    for block in at.subheader:
        parts.append(block.value)
    for block in at.caption:
        parts.append(block.value)
    for block in at.info:
        parts.append(block.value)
    for block in at.warning:
        parts.append(block.value)
    return "\n".join(parts)


def _fill_brief(at: AppTest, service: str = SERVICE_A) -> None:
    at.text_input(key="brief_client").set_value(BRIEF_CLIENT)
    at.text_area(key="brief_task").set_value(BRIEF_TASK)
    at.multiselect(key="brief_services").set_value([service])
    at.number_input(key="brief_deadline_value").set_value(DEADLINE_VALUE)
    at.selectbox(key="brief_deadline_unit").select(DEADLINE_UNIT)
    at.text_input(key="brief_budget").set_value("100 000 руб.")
    at.run()


def _generate(at: AppTest, service: str = SERVICE_A) -> AppTest:
    _fill_brief(at, service)
    _click_label(at, "Сгенерировать КП")
    assert not at.exception
    return at


def _versions(db_path: Path) -> list[dict]:
    proposals = proposal_repository.list_proposals(db_path=db_path)
    assert proposals, "ожидалось хотя бы одно КП"
    return proposal_repository.list_versions(proposals[0]["proposal_id"], db_path=db_path)


def _edit_task(at: AppTest, text: str) -> AppTest:
    at.text_area(key="edit_text_task").set_value(text)
    at.run()
    return at


def _section(draft, key: str):
    return next(section for section in draft.sections if section.key == key)


# --- Извлечение текста из PDF (subset-шрифты: ToUnicode + ASCII85) -----------


def _decode_stream(payload: bytes) -> bytes | None:
    try:
        return zlib.decompress(payload)
    except Exception:
        pass
    stripped = payload.strip()
    if stripped.endswith(b"~>"):
        stripped = stripped[:-2]
    try:
        data = base64.a85decode(stripped, adobe=False)
    except Exception:
        return None
    try:
        return zlib.decompress(data)
    except Exception:
        return data


def _parse_cmap(text: str) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            mapping[int(src, 16)] = chr(int(dst, 16))
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for lo, hi, dst in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block
        ):
            for code in range(int(lo, 16), int(hi, 16) + 1):
                mapping[code] = chr(int(dst, 16) + code - int(lo, 16))
    return mapping


def pdf_text(raw: bytes) -> str:
    """Восстановить читаемый текст PDF (для проверки содержимого)."""
    cmap_by_base: dict[str, dict[int, str]] = {}
    contents: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        decoded = _decode_stream(match.group(1))
        if decoded is None:
            continue
        text = decoded.decode("latin-1")
        if "beginbfchar" in text:
            name = re.search(r"/CMapName /([A-Za-z0-9+\-]+)", text)
            if name:
                cmap_by_base[name.group(1)] = _parse_cmap(text)
            continue
        if " Tf" in text:
            contents.append(text)

    fontmap_base: dict[str, str] = {}
    for match in re.finditer(rb"/(F\d+\+0)\s+(\d+) 0 R", raw):
        name, ref = match.group(1).decode(), int(match.group(2))
        pattern = re.compile(
            (r"(?m)^%d 0 obj(.{0,500}?)/BaseFont /([A-Za-z0-9+\-]+)" % ref).encode(),
            re.S,
        )
        obj = pattern.search(raw)
        if obj:
            fontmap_base[name] = obj.group(2).decode()

    out: list[str] = []
    for text in contents:
        current: dict[int, str] = {}
        for token in re.finditer(r"/(F\d+\+0) [\d.]+ Tf|\((.*?)\) Tj", text, re.S):
            if token.group(1):
                current = cmap_by_base.get(fontmap_base.get(token.group(1), ""), {})
                continue
            value = token.group(2)
            if value is None:
                continue
            out.append(
                re.sub(
                    r"\\([0-7]{3})",
                    lambda mm, c=current: c.get(int(mm.group(1), 8), "?"),
                    value,
                )
            )
    return "".join(out)


# --- A: предпросмотр показывает актуальную версию после правки и сохранения ---


def test_A_preview_shows_saved_version_after_edit(db_path: Path) -> None:
    at = _new_app()
    _generate(at)
    assert len(_versions(db_path)) == 1

    _edit_task(at, EDITED_TASK)
    _click(at, "editor_save")
    assert len(_versions(db_path)) == 2

    _goto(at, SCREEN_PREVIEW)
    assert not at.exception
    text = _render_text(at)
    assert EDITED_TASK in text
    assert "Версия 2" in text
    assert BRIEF_TASK not in text.replace(EDITED_TASK, "")


# --- B: ключевая регрессия — пин старой версии из истории не влияет на новую ---


def test_B_stale_history_pin_does_not_hide_new_version(db_path: Path) -> None:
    at = _new_app()
    _generate(at)
    v1 = _versions(db_path)[0]["id"]

    # Явно открываем предпросмотр версии 1 из истории (закрепляет preview_version_id).
    _goto(at, SCREEN_HISTORY)
    _click(at, "history_open_preview")
    assert at.radio[0].value == SCREEN_PREVIEW
    assert "Версия 1" in _render_text(at)

    # Правка и сохранение новой версии в редакторе.
    _goto(at, SCREEN_DRAFT)
    _edit_task(at, STALE_PIN_USER_TASK)
    _click(at, "editor_save")
    assert len(_versions(db_path)) == 2

    # Предпросмотр должен показывать актуальную версию, а не старую.
    _goto(at, SCREEN_PREVIEW)
    text = _render_text(at)
    assert STALE_PIN_USER_TASK in text
    assert "Версия 2" in text
    assert "старая версия" not in text.lower()

    # Старая версия по-прежнему доступна и не тронута.
    draft_v1 = proposal_repository.get_version(v1, db_path=db_path)
    assert draft_v1 is not None
    assert STALE_PIN_USER_TASK not in _section(draft_v1, "task").text


# --- C: после «перезагрузки» предпросмотр использует последнюю версию ---------


def test_C_preview_after_reload_uses_latest_version(db_path: Path) -> None:
    at = _new_app()
    _generate(at)
    _edit_task(at, EDITED_TASK)
    _click(at, "editor_save")

    reloaded = _new_app()
    _goto(reloaded, SCREEN_PREVIEW)
    assert not reloaded.exception
    assert EDITED_TASK in _render_text(reloaded)
    assert "Версия 2" in _render_text(reloaded)


# --- D: явно выбранная старая версия помечается, актуальная не меняется -------


def test_D_explicit_old_version_is_labelled_and_current_untouched(db_path: Path) -> None:
    at = _new_app()
    _generate(at)
    _edit_task(at, EDITED_TASK)
    _click(at, "editor_save")

    proposal_id = proposal_repository.list_proposals(db_path=db_path)[0]["proposal_id"]
    assert proposal_repository.get_proposal(proposal_id, db_path=db_path)["current_version"] == 2

    _goto(at, SCREEN_HISTORY)
    # Явно выбираем старую версию 1.
    v1_option = next(
        opt for opt in at.selectbox(key="history_version").options
        if opt.startswith("Версия 1 ")
    )
    at.selectbox(key="history_version").select(v1_option)
    at.run()
    _click(at, "history_open_preview")

    text = _render_text(at)
    assert "Версия 1" in text
    assert "старая версия" in text.lower()
    assert "Актуальная версия: 2" in text

    # Актуальная версия КП не изменилась.
    assert proposal_repository.get_proposal(proposal_id, db_path=db_path)["current_version"] == 2


# --- E: открытие предпросмотра не создаёт новую версию -----------------------


def test_E_opening_preview_does_not_create_version(db_path: Path) -> None:
    at = _new_app()
    _generate(at)
    before = len(_versions(db_path))

    _goto(at, SCREEN_PREVIEW)
    _goto(at, SCREEN_HISTORY)
    _goto(at, SCREEN_PREVIEW)

    assert len(_versions(db_path)) == before


# --- F: скачивание PDF не создаёт версию, но помечает её exported ------------


def test_F_download_marks_exported_without_new_version(db_path: Path) -> None:
    at = _new_app()
    _generate(at)
    before = _versions(db_path)
    assert before[0]["status"] == "generated"

    _goto(at, SCREEN_PREVIEW)
    assert at.download_button, "кнопка скачивания PDF должна быть доступна"
    at.download_button[0].click()
    at.run()

    after = _versions(db_path)
    assert len(after) == len(before)
    assert after[-1]["status"] == "exported"


# --- G: старые версии сохраняются --------------------------------------------


def test_G_old_versions_are_preserved(db_path: Path) -> None:
    at = _new_app()
    _generate(at)
    original = _versions(db_path)[0]["id"]
    _edit_task(at, EDITED_TASK)
    _click(at, "editor_save")

    versions = _versions(db_path)
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["id"] == original
    assert proposal_repository.get_version(original, db_path=db_path) is not None


# --- H: коммерческие разделы не редактируются и совпадают с доверенными данными


def test_H_commercial_sections_readonly_and_trusted(db_path: Path) -> None:
    at = _new_app()
    _generate(at)

    before = proposal_repository.get_latest_draft(db_path=db_path)
    pricing_before = _section(before, "pricing").text
    deadlines_before = _section(before, "deadlines").text

    # В редакторе коммерческие разделы отображаются текстом, а не полем ввода.
    widget_keys = {area.key for area in at.text_area}
    assert "edit_text_pricing" not in widget_keys
    assert "edit_text_deadlines" not in widget_keys

    _edit_task(at, EDITED_TASK)
    _click(at, "editor_save")

    after = proposal_repository.get_latest_draft(db_path=db_path)
    assert _section(after, "pricing").text == pricing_before
    assert _section(after, "deadlines").text == deadlines_before
    assert _section(after, "pricing").source == "code"
    assert "500 руб." in _section(after, "pricing").text
    assert "30" in _section(after, "deadlines").text
    assert "дней" in _section(after, "deadlines").text


# --- I: PDF содержит отредактированный текст и не содержит служебных пометок --


def test_I_pdf_contains_edited_text_without_service_notes(db_path: Path) -> None:
    at = _new_app()
    _generate(at)
    _edit_task(at, EDITED_TASK)
    _click(at, "editor_save")

    draft = proposal_repository.get_latest_draft(db_path=db_path)
    raw = pdf.build_pdf(draft, BRIEF_CLIENT)
    text = pdf_text(raw)

    assert raw[:5] == b"%PDF-"
    assert pdf.pdf_page_count(raw) >= 1
    assert EDITED_TASK in text
    assert "500 руб." in text
    assert "Требует уточнения" not in text
    assert "требует уточнения" not in text.lower()
    assert "разработке" not in text.lower()


# --- J: сохранение без изменений не создаёт версию ---------------------------


def test_J_save_without_changes_creates_no_version(db_path: Path) -> None:
    at = _new_app()
    _generate(at)
    before = len(_versions(db_path))

    _click(at, "editor_save")

    assert len(_versions(db_path)) == before
    assert any("Изменений нет" in msg.value for msg in at.success)

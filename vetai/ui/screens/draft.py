"""Экран «Черновик» — редактор КП (REQ-15..REQ-17).

Основную часть экрана занимает широкий редактор КП. Клиент, версия и дата
сохранения показаны компактно под заголовком. Коммерческие разделы (стоимость,
сроки) показываются только для чтения: они формируются кодом из прайса/брифа.
Прочие разделы доступны для ручного редактирования. Сохранение изменённого
текста создаёт новую версию ``edited`` (старые версии не меняются).

Защитные проверки не изменяются (см. ``services.export_checks``). Критические
замечания, блокирующие экспорт, остаются заметными на экране предпросмотра/PDF
рядом с действием экспорта. Некритические замечания показаны под редактором в
одном сворачиваемом блоке «Рекомендации по улучшению» (по умолчанию закрыт);
все уникальные замечания доступны без потери информации.
"""

from __future__ import annotations

import json
import re

import streamlit as st

from vetai.models import (
    CODE_SECTION_KEYS,
    SOURCE_CODE,
    SOURCE_MANUAL,
    SOURCE_PLACEHOLDER,
    DraftSection,
    ProposalDraft,
)
from vetai.repositories import brief_repository, proposal_repository
from vetai.services import commercial, export_checks

_SECTION_RE = re.compile(r"«([^»]+)»")


def _resolve_draft() -> ProposalDraft | None:
    version_id = st.session_state.get("editor_version_id")
    if version_id is not None:
        draft = proposal_repository.get_version(version_id)
        if draft is not None:
            return draft
    return proposal_repository.get_latest_draft()


def _ensure_state(draft: ProposalDraft) -> None:
    if st.session_state.get("editor_base_version_id") == draft.version_id:
        return
    st.session_state["editor_base_version_id"] = draft.version_id
    st.session_state["editor_proposal_id"] = draft.proposal_id
    st.session_state["editor_sections"] = [
        {
            "key": s.key,
            "title": s.title,
            "text": s.text,
            "source": s.source,
        }
        for s in draft.sections
    ]
    st.session_state["editor_snapshot"] = dict(draft.commercial_snapshot)
    st.session_state["editor_dirty"] = False
    st.session_state["unsaved_changes"] = False
    for section in draft.sections:
        st.session_state[f"edit_text_{section.key}"] = section.text


# --- Контекст документа ----------------------------------------------------


def _client_name(draft: ProposalDraft) -> str:
    brief = brief_repository.get_brief(draft.brief_id)
    return brief.client if brief is not None else ""


# --- Блокировка перехода при несохранённых изменениях ----------------------


def _render_blocked_notice() -> None:
    target = st.session_state.pop("nav_blocked_target", None)
    if target:
        st.warning(
            "Переход отменён: есть несохранённые изменения. Сохраните их или выйдите без сохранения."
        )
        cols = st.columns(2)
        if cols[0].button("Выйти без сохранения", key="editor_leave_without_save"):
            st.session_state["unsaved_changes"] = False
            st.session_state["nav_blocked_target"] = None
            st.session_state["pending_screen"] = target
            st.rerun()
        if cols[1].button("Остаться в редакторе", key="editor_stay"):
            st.session_state["nav_blocked_target"] = None
            st.rerun()


# --- Проверка КП (некритические рекомендации) ------------------------------


def _current_sections(draft: ProposalDraft) -> list[DraftSection]:
    result: list[DraftSection] = []
    for section in st.session_state.get("editor_sections", []):
        key = section["key"]
        title = section["title"]
        if key in CODE_SECTION_KEYS:
            text = section["text"]
            source = SOURCE_CODE
        else:
            text = st.session_state.get(f"edit_text_{key}", section["text"])
            if not text.strip():
                source = SOURCE_PLACEHOLDER
                text = ""
            else:
                source = SOURCE_MANUAL
        result.append(DraftSection(key=key, title=title, text=text, source=source))
    return result


def _collect_warnings(draft: ProposalDraft) -> list[str]:
    """Собрать уникальные некритические замечания защитной проверки."""
    current = _current_sections(draft)
    snapshot = st.session_state.get("editor_snapshot") or dict(
        draft.commercial_snapshot
    )
    check = export_checks.check_sections(current, snapshot)
    warnings: list[str] = []
    seen: set[str] = set()
    for message in check.warnings:
        if message not in seen:
            seen.add(message)
            warnings.append(message)
    return warnings


def _group_warnings(warnings: list[str]) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for message in warnings:
        match = _SECTION_RE.search(message)
        name = match.group(1) if match else "Общие замечания"
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append(message)
    return [(name, groups[name]) for name in order]


# --- Документ (центральная зона) -------------------------------------------


def _render_actions(draft: ProposalDraft) -> None:
    dirty = _is_dirty(draft)
    st.session_state["editor_dirty"] = dirty
    st.session_state["unsaved_changes"] = dirty

    with st.container(key="editor_actions", horizontal=True, gap="small"):
        if st.button(
            "Сохранить изменения",
            key="editor_save",
            type="primary",
            icon=":material/save:",
        ):
            _save(draft)
            st.rerun()
        if st.button(
            "Пересчитать стоимость и сроки",
            key="editor_refresh_commercial",
            icon=":material/refresh:",
        ):
            _refresh_commercial(draft)
            st.rerun()
    if dirty:
        st.caption("Есть несохранённые изменения.")


def _render_canvas(draft: ProposalDraft) -> None:
    sections = st.session_state.get("editor_sections", [])
    for index, section in enumerate(sections, start=1):
        key = section["key"]
        locked = key in CODE_SECTION_KEYS
        head_cols = st.columns([1, 0.32], gap="small", vertical_alignment="center")
        with head_cols[0]:
            st.subheader(f"{index:02d}. {section['title']}")
        with head_cols[1]:
            with st.container(key=f"doc_tag_{index}"):
                st.caption("Защищённый блок" if locked else "Текстовый раздел")
        if locked:
            with st.container(key=f"doc_locked_{key}"):
                for line in section["text"].splitlines():
                    if line.strip():
                        st.markdown(line)
                st.caption(
                    "Заполняется автоматически по прайсу и брифу — вручную не редактируется."
                )
        else:
            st.text_area(
                section["title"],
                key=f"edit_text_{key}",
                height=100,
                label_visibility="collapsed",
                placeholder="Заполните раздел",
            )
        if index != len(sections):
            st.divider()


def _render_head(draft: ProposalDraft | None) -> None:
    """Шапка документа: надзаголовок, крупный заголовок, метаданные."""
    with st.container(key="editor_head"):
        st.markdown("РЕДАКТОР КП")
        st.markdown("### Коммерческое предложение")
        if draft is not None:
            client = _client_name(draft)
            created = draft.created_at.astimezone().strftime("%d.%m.%Y %H:%M")
            meta = [f"Версия: {draft.version}", f"Сохранено: {created}"]
            if client:
                meta.insert(0, f"Клиент: {client}")
            st.caption(" · ".join(meta))


def _render_document(draft: ProposalDraft, flash: str | None = None) -> None:
    _render_head(draft)
    if flash:
        st.success(flash)
    _render_actions(draft)
    with st.container(key="doc_canvas"):
        _render_canvas(draft)


# --- Рекомендации (сворачиваемый блок под редактором) ----------------------


def _render_recommendations(draft: ProposalDraft) -> None:
    warnings = _collect_warnings(draft)
    if not warnings:
        return
    with st.expander("Рекомендации по улучшению", expanded=False):
        for name, group in _group_warnings(warnings):
            st.markdown(f"*{name}*")
            for message in group:
                st.write(message)


# --- Изменения версии ------------------------------------------------------


def _normalize(text: str) -> str:
    return (text or "").strip()


def _is_dirty(draft: ProposalDraft) -> bool:
    current = _current_sections(draft)
    base_by_key = {s.key: s for s in draft.sections}
    for sec in current:
        b = base_by_key.get(sec.key)
        if b is None:
            return True
        if _normalize(sec.text) != _normalize(b.text):
            return True
    return False


def _refresh_commercial(draft: ProposalDraft) -> None:
    brief = brief_repository.get_brief(draft.brief_id)
    sections = st.session_state.get("editor_sections", [])
    if brief is None:
        st.warning("Бриф не найден — нельзя обновить коммерческий блок.")
        return
    data = commercial.build_commercial_data(brief.services, brief.deadlines)
    texts = {
        "pricing": commercial.render_price_section(data),
        "deadlines": commercial.render_deadline_section(data.deadlines_text),
    }
    changed = False
    for section in sections:
        if section["key"] in texts:
            new_text = texts[section["key"]]
            if section["text"] != new_text:
                changed = True
            section["text"] = new_text
            section["source"] = SOURCE_CODE
    st.session_state["editor_sections"] = sections
    st.session_state["editor_snapshot"] = commercial.build_snapshot(
        data, brief.deadlines
    )
    st.session_state["draft_flash"] = (
        "Стоимость и сроки пересчитаны. Нажмите «Сохранить изменения», "
        "чтобы сохранить новую версию КП."
        if changed
        else "Стоимость и сроки уже актуальны — изменения не требуются."
    )


def _save(draft: ProposalDraft) -> None:
    current = _current_sections(draft)
    dirty = _is_dirty(draft)
    if not dirty:
        st.session_state["draft_flash"] = "Изменений нет — новая версия не создана."
        return
    snapshot = st.session_state.get("editor_snapshot") or dict(
        draft.commercial_snapshot
    )
    check = export_checks.check_sections(current, snapshot)
    warnings: list[str] = list(check.warnings)
    issues: list[str] = list(check.critical)
    for sec in current:
        if sec.source == SOURCE_PLACEHOLDER:
            note = f"Раздел «{sec.title}» требует уточнения."
            if note not in warnings and note not in issues:
                warnings.append(note)
    new_body = {
        "provider": draft.provider,
        "sections": [
            {
                "key": s.key,
                "title": s.title,
                "text": s.text,
                "source": s.source,
            }
            for s in current
        ],
        "warnings": warnings,
        "validation": {"issues": issues},
    }
    body_json = json.dumps(new_body, ensure_ascii=False)
    snap_json = json.dumps(snapshot, ensure_ascii=False)
    version_id_new, version_new = proposal_repository.append_edited_version(
        draft.proposal_id, body_json, snap_json
    )
    st.session_state["editor_version_id"] = version_id_new
    st.session_state["editor_base_version_id"] = None
    st.session_state.pop("preview_version_id", None)
    st.session_state["draft_flash"] = f"Сохранено: создана версия {version_new}."


def render() -> None:
    flash = st.session_state.pop("draft_flash", None)

    draft = _resolve_draft()
    if draft is None:
        _render_head(None)
        if flash:
            st.success(flash)
        st.info(
            "Черновик ещё не сгенерирован. Заполните бриф на экране «Бриф» и нажмите «Сгенерировать КП»."
        )
        return

    _ensure_state(draft)
    _render_blocked_notice()
    _render_document(draft, flash)
    _render_recommendations(draft)

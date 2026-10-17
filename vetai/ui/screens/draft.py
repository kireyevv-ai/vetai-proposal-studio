"""Экран «Черновик» — редактор КП (REQ-15..REQ-17).

Показывает текущую версию КП: коммерческие разделы (стоимость, сроки) —
только для чтения (формируются кодом из прайса/брифа), прочие разделы — доступны
для ручного редактирования. Сохранение изменённого текста создаёт новую версию
``edited`` (без изменения старых версий). Предупреждения защитных проверок
выводятся отдельно от текста КП.
"""

from __future__ import annotations

import json

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


def _render_meta(draft: ProposalDraft) -> None:
    created = draft.created_at.astimezone().strftime("%d.%m.%Y %H:%M")
    st.caption(
        f"Версия {draft.version} · статус: {draft.status} · провайдер: «{draft.provider}» · создано: {created} · бриф ID {draft.brief_id} · КП ID {draft.proposal_id}."
    )
    st.caption(
        "Коммерческие разделы (Стоимость, Сроки) формируются программой из прайса и брифа (REQ-10, REQ-12) — не редактируются вручную."
    )


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


def _render_warnings(draft: ProposalDraft) -> None:
    if draft.warnings:
        st.warning("Требует ручной проверки:")
        for warning in draft.warnings:
            st.write(f"- {warning}")


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


def _render_sections(draft: ProposalDraft) -> None:
    for section in st.session_state.get("editor_sections", []):
        st.subheader(section["title"])
        key = section["key"]
        if key in CODE_SECTION_KEYS:
            st.text(section["text"])
            st.caption(
                "Раздел формируется программой из доверенных данных (прайс, бриф) и не редактируется вручную (REQ-10, REQ-12)."
            )
        else:
            st.text_area(
                section["title"],
                key=f"edit_text_{key}",
                height=140,
                label_visibility="collapsed",
            )
            if section["source"] == SOURCE_PLACEHOLDER and not st.session_state.get(
                f"edit_text_{key}", ""
            ).strip():
                st.info(
                    "Требует уточнения: для этого раздела нет доверенных данных. Заполните вручную (REQ-16)."
                )
        st.divider()


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
        "Коммерческий блок обновлён из доверенных данных. Нажмите «Сохранить изменения»."
        if changed
        else "Коммерческий блок уже соответствует доверенным данным."
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
    st.session_state["draft_flash"] = f"Сохранено: создана версия {version_new} (статус: edited)."


def _render_actions(draft: ProposalDraft) -> None:
    dirty = _is_dirty(draft)
    st.session_state["editor_dirty"] = dirty
    st.session_state["unsaved_changes"] = dirty

    if dirty:
        st.warning("Есть несохранённые изменения — не забудьте сохранить.")

    cols = st.columns(3)
    if cols[0].button("Сохранить изменения", key="editor_save"):
        _save(draft)
        st.rerun()
    if cols[1].button("Обновить коммерческий блок из доверенных данных", key="editor_refresh_commercial"):
        _refresh_commercial(draft)
        st.rerun()
    if cols[2].button("Обновить", key="editor_refresh_view"):
        st.rerun()


def render() -> None:
    st.header("Черновик с редактором")

    flash = st.session_state.pop("draft_flash", None)
    if flash:
        st.success(flash)

    draft = _resolve_draft()
    if draft is None:
        st.info(
            "Черновик ещё не сгенерирован. Заполните бриф на экране «Бриф» и нажмите «Сгенерировать КП»."
        )
        return

    _ensure_state(draft)
    _render_blocked_notice()
    _render_meta(draft)
    _render_warnings(draft)
    _render_sections(draft)
    _render_actions(draft)
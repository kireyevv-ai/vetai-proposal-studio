"""Экран «Предпросмотр и PDF» (REQ-18..REQ-21).

Предпросмотр строится из последней сохранённой версии КП. Перед экспортом
выполняется защитная проверка (критические ошибки блокируют, предупреждения —
не блокируют). PDF формируется через ReportLab без служебных сообщений.
"""

from __future__ import annotations

import re

import streamlit as st

from vetai.deadlines import UNIT_LABELS, UNIT_LABEL_TO_KEY
from vetai.models import SOURCE_PLACEHOLDER
from vetai.repositories import brief_repository, proposal_repository
from vetai.services import deadline_fix, export_checks, pdf


def _resolve_draft():
    version_id = st.session_state.get("preview_version_id")
    if version_id is not None:
        draft = proposal_repository.get_version(version_id)
        if draft is not None:
            return draft
    return proposal_repository.get_latest_draft()


def _client_name(brief_id: int) -> str:
    brief = brief_repository.get_brief(brief_id)
    return brief.client if brief else ""


def _file_name(client: str) -> str:
    clean = re.sub(r"[^\w\-\. ]+", "", client).strip()
    clean = re.sub(r"\s+", " ", clean)
    if not clean:
        return "Коммерческое_предложение.pdf"
    return f"КП_{clean}.pdf"


def _render_deadline_resolution(draft) -> None:
    """Уточнить единицу срока для старой версии КП (Часть Б, без автоназначения)."""
    if not deadline_fix.needs_unit(draft):
        return

    value, _unit = deadline_fix.legacy_deadline(draft)
    st.warning(
        "Срок указан без единицы измерения — это старая запись. "
        "Уточните единицу, чтобы разблокировать экспорт."
    )
    st.caption(
        f"Обнаружен срок: {value}. Единица измерения не назначается автоматически — "
        "выберите её явно."
    )
    labels = list(UNIT_LABELS.values())
    choice = st.selectbox(
        "Единица измерения срока",
        labels,
        index=None,
        placeholder="Выберите единицу измерения",
        key="deadline_fix_unit",
    )
    if st.button(
        "Подтвердить срок и создать новую версию",
        key="deadline_fix_confirm",
        disabled=choice is None,
    ):
        try:
            version_id, version = deadline_fix.create_corrected_version(
                draft, UNIT_LABEL_TO_KEY[choice]
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["preview_version_id"] = version_id
            st.session_state["draft_flash"] = (
                f"Срок уточнён: создана новая версия {version}. "
                "Предпросмотр и PDF используют её."
            )
            st.rerun()


def render() -> None:
    st.header("Предпросмотр и PDF")

    draft = _resolve_draft()
    if draft is None:
        st.info(
            "Нет сохранённого КП для предпросмотра. Сначала сгенерируйте черновик на экране «Бриф»/«Черновик»."
        )
        return

    client = _client_name(draft.brief_id)
    created = draft.created_at.astimezone().strftime("%d.%m.%Y %H:%M")

    st.caption(f"Версия {draft.version} · создана: {created}.")

    proposal = proposal_repository.get_proposal(draft.proposal_id)
    current_version = int(proposal["current_version"]) if proposal else None
    if current_version is not None and draft.version != current_version:
        st.warning(
            f"Показана старая версия {draft.version} — выбрана вручную в истории. "
            f"Актуальная версия: {current_version}. PDF будет именно из версии {draft.version}."
        )

    st.subheader("Предпросмотр (как в PDF)")
    st.markdown("**VETAI — Коммерческое предложение**")
    meta = []
    if client:
        meta.append(f"Клиент: {client}")
    meta.append(f"Дата: {draft.created_at.astimezone().strftime('%d.%m.%Y')}")
    st.write(" · ".join(meta))
    st.divider()

    for section in draft.sections:
        if section.source == SOURCE_PLACEHOLDER or not section.text.strip():
            continue
        st.subheader(section.title)
        for line in section.text.splitlines():
            if not line.strip():
                st.write("")
                continue
            st.write(line.strip())
        st.divider()

    st.subheader("Экспорт PDF")
    check = export_checks.check_for_export(draft)

    if check.critical:
        st.error("Экспорт заблокирован. Устраните критические замечания:")
        for c in check.critical:
            st.write(f"- {c}")
        _render_deadline_resolution(draft)
        return

    if check.warnings:
        st.warning("Требует ручной проверки (не блокирует экспорт):")
        for w in check.warnings:
            st.write(f"- {w}")

    _render_deadline_resolution(draft)

    pdf_bytes = pdf.build_pdf(draft, client)
    if st.download_button(
        "Скачать PDF",
        data=pdf_bytes,
        file_name=_file_name(client),
        mime="application/pdf",
        key="preview_download",
    ):
        try:
            proposal_repository.mark_version_exported(draft.version_id)
        except Exception:
            pass

    st.caption(
        "Предупреждения защитных проверок выводятся только здесь и не "
        "попадают в PDF. Автоматические проверки не гарантируют обнаружение "
        "всех ошибок — перед отправкой проверьте документ."
    )
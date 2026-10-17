"""Экран «Черновик».

Показывает последний сгенерированный черновик КП (REQ-15). На этом этапе экран
**только для чтения**: коммерческие разделы (стоимость, сроки) сформированы
кодом из доверенных данных (REQ-10, REQ-12), текстовые — AI-провайдером.
Предупреждения защитных проверок отражаются пользователю (REQ-13). Ручное
редактирование будет добавлено на следующем этапе (REQ-16).
"""

from __future__ import annotations

import streamlit as st

from vetai.models import SOURCE_CODE, SOURCE_PLACEHOLDER
from vetai.repositories import proposal_repository


def render() -> None:
    st.header("Черновик с редактором")

    flash = st.session_state.pop("draft_flash", None)
    if flash:
        st.success(flash)

    draft = proposal_repository.get_latest_draft()
    if draft is None:
        st.info(
            "Черновик ещё не сгенерирован. Заполните бриф на экране «Бриф» и "
            "нажмите «Сгенерировать КП»."
        )
        st.caption("Планируемый этап редактора: следующий. Требования: REQ-15..REQ-17.")
        return

    created = draft.created_at.astimezone().strftime("%d.%m.%Y %H:%M")
    st.caption(
        f"Версия {draft.version} · статус: {draft.status} · провайдер: "
        f"«{draft.provider}» · создано: {created} · бриф ID {draft.brief_id}."
    )
    st.caption(
        "Коммерческие разделы (стоимость, сроки) заполнены программой из прайса "
        "и брифа — модель их не формирует (REQ-10, REQ-12). Разделы без "
        "доверенных данных помечены как «требует уточнения»."
    )

    if draft.warnings:
        st.warning("Требует ручной проверки:")
        for warning in draft.warnings:
            st.write(f"- {warning}")

    for section in draft.sections:
        st.subheader(section.title)
        if section.source == SOURCE_PLACEHOLDER:
            st.info(
                "Требует уточнения: для этого раздела нет доверенных данных, "
                "он не формируется моделью. Заполните вручную на этапе редактора "
                "(REQ-16)."
            )
        else:
            st.write(section.text)
            if section.source == SOURCE_CODE:
                st.caption("Раздел сформирован программой из доверенных данных.")
        st.divider()

    st.info(
        "Редактирование текста КП появится на следующем этапе (REQ-16). "
        "Сейчас экран показывает результат генерации только для чтения."
    )

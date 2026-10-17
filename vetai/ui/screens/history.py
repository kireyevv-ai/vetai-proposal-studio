"""Экран «История КП» (REQ-22..REQ-25).

Список сохранённых коммерческих предложений с версией и датой; возможность
открыть ранее сохранённое КП и его версии. Не реализует полный CRM, сложные
статусы и роли.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from vetai.repositories import proposal_repository


def _fmt_iso(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M")
    except Exception:
        try:
            return value.replace("T", " ").replace("Z", "")
        except Exception:
            return str(value)


def render() -> None:
    st.header("История КП")

    proposals = proposal_repository.list_proposals()
    if not proposals:
        st.info("Сохранённых коммерческих предложений пока нет. Сгенерируйте КП на экране «Бриф»/«Черновик».")
        return

    rows = []
    for p in proposals:
        rows.append(
            {
                "КП": f"#{p['proposal_id']}",
                "Клиент": p["client"],
                "Текущая версия": p["current_version"],
                "Статус текущей": p["status"],
                "Обновлено": _fmt_iso(p["updated_at"]),
                "Всего версий": p["versions_count"],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    labels = {
        f"#{p['proposal_id']} — {p['client']} (версия {p['current_version']})": p
        for p in proposals
    }
    choice = st.selectbox("Выберите КП", list(labels), key="history_proposal")
    proposal = labels[choice]

    versions = proposal_repository.list_versions(proposal["proposal_id"])
    if not versions:
        st.warning("Нет версий для выбранного КП.")
        return

    vlabels = {
        f"Версия {v['version']} · {v['status']} · {_fmt_iso(v['created_at'])}": v
        for v in versions
    }
    vchoice = st.selectbox("Выберите версию", list(vlabels), key="history_version")
    version = vlabels[vchoice]

    cols = st.columns(2)
    if cols[0].button("Открыть в редакторе", key="history_open_editor"):
        st.session_state["editor_version_id"] = version["id"]
        st.session_state["pending_screen"] = "Черновик"
        st.rerun()

    if cols[1].button("Предпросмотр", key="history_open_preview"):
        st.session_state["preview_version_id"] = version["id"]
        st.session_state["pending_screen"] = "Предпросмотр и PDF"
        st.rerun()

    st.caption(
        "Доступны ранее сохранённые версии КП; редактирование открытой версии создаст новую версию с тем же номером расчёта текущей версии (добавляется новая версия)."
    )
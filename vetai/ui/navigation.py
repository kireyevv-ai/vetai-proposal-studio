"""Навигация между экранами приложения.

Четыре экрана из ТЗ школы (Бриф, Черновик, Предпросмотр и PDF, История КП)
плюс служебный экран «Настройки» для прайса и шаблона (REQ-29, OQ-02).
Навигация не имитирует работу неразработанных экранов — они сами сообщают статус.
"""

from __future__ import annotations

import base64

import streamlit as st

from vetai.config import LOGO_PATH

SCREEN_BRIEF = "Бриф"
SCREEN_DRAFT = "Черновик"
SCREEN_PREVIEW = "Предпросмотр и PDF"
SCREEN_HISTORY = "История КП"
SCREEN_SETTINGS = "Настройки"

SCREENS: tuple[str, ...] = (
    SCREEN_BRIEF,
    SCREEN_DRAFT,
    SCREEN_PREVIEW,
    SCREEN_HISTORY,
    SCREEN_SETTINGS,
)


def _on_nav_change() -> None:
    target = st.session_state.get("nav_screen")
    if not st.session_state.get("unsaved_changes"):
        return
    if target == SCREEN_DRAFT:
        return
    st.session_state["nav_screen"] = SCREEN_DRAFT
    st.session_state["nav_blocked_target"] = target


def render_navigation() -> str:
    """Нарисовать боковую навигацию и вернуть выбранный экран."""
    # Переход на другой экран, запрошенный предыдущим запуском (например, после
    # генерации открываем «Черновик»). Выполняется ДО создания виджета radio,
    # иначе изменение ключа nav_screen было бы запрещено Streamlit.
    pending = st.session_state.pop("pending_screen", None)
    if pending in SCREENS:
        st.session_state["nav_screen"] = pending
    # Снять флаг заблокированного перехода при явном навигации
    st.session_state.pop("nav_blocked_target", None)

    # Логотип уже содержит название бренда — отдельную надпись не дублируем.
    if LOGO_PATH.exists():
        with st.sidebar.container(key="brand"):
            logo_data = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
            st.markdown(
                f'<img src="data:image/png;base64,{logo_data}" alt="VETAI"'
                f' style="display:block; width:100%; height:auto; margin:0 auto;" />',
                unsafe_allow_html=True,
            )
            st.caption("Конструктор КП")
    else:
        st.sidebar.title("VETAI")
        st.sidebar.caption("Конструктор КП")
    choice = st.sidebar.radio(
        "Навигация", SCREENS, key="nav_screen", on_change=_on_nav_change
    )
    return choice

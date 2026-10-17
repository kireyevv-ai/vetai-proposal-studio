"""Навигация между экранами приложения.

Четыре экрана из ТЗ школы (Бриф, Черновик, Предпросмотр и PDF, История КП)
плюс служебный экран «Настройки» для прайса и шаблона (REQ-29, OQ-02).
Навигация не имитирует работу неразработанных экранов — они сами сообщают статус.
"""

from __future__ import annotations

import streamlit as st

from vetai.config import APP_TITLE

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


def render_navigation() -> str:
    """Нарисовать боковую навигацию и вернуть выбранный экран."""
    st.sidebar.title(APP_TITLE)
    st.sidebar.caption("Учебный AI-конструктор коммерческих предложений")
    choice = st.sidebar.radio("Навигация", SCREENS, key="nav_screen")
    st.sidebar.divider()
    st.sidebar.caption(
        "Реализованы: бриф, прайс и шаблон КП (экран «Настройки»). "
        "Генерация, редактор и PDF будут реализованы на следующих этапах."
    )
    return choice

"""Навигация между четырьмя экранами приложения.

Экраны соответствуют ТЗ школы: Бриф, Черновик, Предпросмотр и PDF, История КП.
Навигация не имитирует работу неразработанных экранов — они сами сообщают статус.
"""

from __future__ import annotations

import streamlit as st

from vetai.config import APP_TITLE

SCREEN_BRIEF = "Бриф"
SCREEN_DRAFT = "Черновик"
SCREEN_PREVIEW = "Предпросмотр и PDF"
SCREEN_HISTORY = "История КП"

SCREENS: tuple[str, ...] = (
    SCREEN_BRIEF,
    SCREEN_DRAFT,
    SCREEN_PREVIEW,
    SCREEN_HISTORY,
)


def render_navigation() -> str:
    """Нарисовать боковую навигацию и вернуть выбранный экран."""
    st.sidebar.title(APP_TITLE)
    st.sidebar.caption("Учебный AI-конструктор коммерческих предложений")
    choice = st.sidebar.radio("Навигация", SCREENS, key="nav_screen")
    st.sidebar.divider()
    st.sidebar.caption(
        "Текущий этап: каркас приложения, база данных и форма брифа. "
        "Генерация, редактор и PDF будут реализованы на следующих этапах."
    )
    return choice

"""Точка входа приложения VETAI Proposal Studio.

Запуск: ``streamlit run app.py``

Реализованы каркас, база данных, форма брифа и настройки (прайс и шаблон КП).
Экраны «Черновик», «Предпросмотр и PDF» и «История КП» сообщают о статусе
разработки.
"""

from __future__ import annotations

import streamlit as st

from vetai.config import APP_TITLE
from vetai.db import init_database
from vetai.ui import navigation
from vetai.ui.screens import brief, draft, history, preview, settings


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")

    init_database()
    brief.ensure_state()

    screen = navigation.render_navigation()

    if screen == navigation.SCREEN_BRIEF:
        brief.render()
    elif screen == navigation.SCREEN_DRAFT:
        draft.render()
    elif screen == navigation.SCREEN_PREVIEW:
        preview.render()
    elif screen == navigation.SCREEN_HISTORY:
        history.render()
    elif screen == navigation.SCREEN_SETTINGS:
        settings.render()


main()

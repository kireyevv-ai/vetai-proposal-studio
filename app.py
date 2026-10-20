"""Точка входа приложения VETAI Proposal Studio.

Запуск: ``streamlit run app.py``

Экраны: бриф, черновик КП, предпросмотр и PDF, история КП, настройки
(прайс услуг и шаблон структуры КП).
"""

from __future__ import annotations

import streamlit as st

from vetai.config import APP_TITLE
from vetai.db import init_database
from vetai.ui import navigation, theme
from vetai.ui.screens import brief, draft, history, preview, settings


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    theme.apply_theme()

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

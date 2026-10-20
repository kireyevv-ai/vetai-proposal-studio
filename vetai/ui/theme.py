"""Централизованная визуальная тема приложения.

Направление: Quiet Luxury + функциональный Corporate Precision — светлый
сдержанный B2B-интерфейс со спокойными поверхностями и тёмно-изумрудными
акцентами.

Базовые цвета и шрифты задаются нативными средствами Streamlit
(``.streamlit/config.toml``). Здесь — минимальный CSS для того, что настройки
темы не покрывают: ширина рабочей области, отступы, типографика заголовков и
мягкие поверхности.

CSS опирается только на устойчивые точки: базовые теги и атрибуты
``data-testid`` / ``role``. Селекторы по автоматически генерируемым CSS-классам
не используются, чтобы стиль не ломался при обновлении Streamlit.
"""

from __future__ import annotations

import streamlit as st

_CSS = """
<style>
:root {
    --vetai-bg: #F7F7F4;
    --vetai-surface: #FFFFFF;
    --vetai-text: #17221F;
    --vetai-muted: #67736E;
    /* Повышенный контраст для мелких второстепенных подписей (12–13px):
       #4E5A55 даёт ≈6.7:1 на фоне #F7F7F4 (WCAG AA). */
    --vetai-muted-strong: #4E5A55;
    --vetai-accent: #173F36;
    --vetai-border: #E3E7E3;
    --vetai-heading-font: Georgia, "Times New Roman", serif;
}

/* --- Общий фон и рабочая область --- */
.stApp {
    background: var(--vetai-bg);
    color: var(--vetai-text);
}
[data-testid="stHeader"] {
    background: transparent;
}
[data-testid="stMainBlockContainer"] {
    max-width: 1080px !important;
    padding-top: 0.5rem;
    padding-bottom: 2rem;
}

/* --- Типографика заголовков страниц и подзаголовков --- */
h1, h2, h3, h4 {
    font-family: var(--vetai-heading-font);
    color: var(--vetai-text);
    font-weight: 600;
}
h1 { font-size: 2.1rem; letter-spacing: -0.005em; }
h2 { font-size: 1.6rem; letter-spacing: 0; }
h3 { font-size: 1.2rem; letter-spacing: 0; }
h4 { font-size: 1.05rem; letter-spacing: 0; }

/* --- Вторичный текст и разделители --- */
[data-testid="stCaptionContainer"] p {
    color: var(--vetai-muted);
}
hr {
    border-color: var(--vetai-border);
}

/* --- Боковая навигация --- */
[data-testid="stSidebar"] {
    background: var(--vetai-surface);
    border-right: 1px solid var(--vetai-border);
    /* Компактная боковая панель: логотип + навигация (настройки ширины
       нативными средствами темы нет). Только width — min-width здесь
       нельзя задавать: штатное сворачивание Streamlit приводит min/max-width
       к 0, и ненулевой min-width !important оставлял бы пустую колонку. */
    width: 16rem !important;
}
[data-testid="stSidebar"] [role="radiogroup"] {
    gap: 0.05rem;
}
[data-testid="stSidebar"] [role="radiogroup"] label {
    padding: 0.15rem 0;
}
[data-testid="stSidebar"] h1 {
    font-size: 1.3rem;
    letter-spacing: 0.01em;
}
/* Переснять лишний верхний отступ: уменьшаем высоту «шапки» сайдбара, чтобы
   поднять бренд-блок. Чтобы заголовок «Навигация» и пункты меню не сместились,
   освобождённое место возвращается отступом снизу у бренд-блока. */
[data-testid="stSidebarHeader"] {
    height: 1.75rem;
    min-height: 1.75rem;
    margin-bottom: 0;
}
.st-key-brand {
    padding-bottom: 54px;
}
.st-key-brand [data-testid="stImage"] {
    display: flex;
    justify-content: center;
}
.st-key-brand [data-testid="stImage"] img {
    display: block;
    margin: 0 auto;
}
.st-key-brand [data-testid="stCaptionContainer"] p {
    color: var(--vetai-text);
    font-size: 20px;
    font-weight: 600;
    line-height: 1.1;
    letter-spacing: 0.14em;
    text-align: center;
    white-space: nowrap;
    margin: 7px 0 0;
}

/* --- Кнопки --- */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button {
    font-weight: 600;
    border-radius: 0.5rem;
    padding-top: 0.45rem;
    padding-bottom: 0.45rem;
}

/* --- Поля ввода, выпадающие списки --- */
[data-testid="stTextInput"],
[data-testid="stNumberInput"],
[data-testid="stTextArea"],
[data-testid="stSelectbox"],
[data-testid="stMultiSelect"] {
    font-size: 0.95rem;
}

/* --- Таблицы --- */
[data-testid="stDataFrame"] {
    border: 1px solid var(--vetai-border);
    border-radius: 0.5rem;
    overflow: hidden;
}

/* --- Системные уведомления --- */
[data-testid="stAlert"] {
    border-radius: 0.5rem;
}

/* --- Раскрывающиеся блоки и вкладки --- */
[data-testid="stExpander"] details {
    border: 1px solid var(--vetai-border);
    border-radius: 0.5rem;
    background: var(--vetai-surface);
}
[data-testid="stTabs"] [role="tablist"] {
    /* Явное расстояние: подписи «Услуги и цены» и «Шаблон КП» не должны
       восприниматься как одна фраза. */
    gap: 1.25rem;
    border-bottom: 1px solid var(--vetai-border);
}
[data-testid="stTabs"] [role="tab"] {
    font-weight: 600;
}

/* --- Рабочая область редактора: холст документа --- */
.st-key-doc_canvas {
    background: var(--vetai-surface);
    border: 1px solid var(--vetai-border) !important;
    border-radius: 0.75rem;
    padding: 1.5rem 1.75rem 0.75rem;
    box-shadow: 0 1px 2px rgba(23, 34, 31, 0.04);
}
.st-key-doc_canvas [data-testid="stVerticalBlock"] {
    gap: 0.5rem;
}
/* Заголовки разделов внутри документа. Селектор ограничен холстом, поэтому
   заголовок «Коммерческое предложение» и заголовки других страниц не
   затрагиваются. */
.st-key-doc_canvas h3 {
    font-size: 25px;
    line-height: 1.2;
    letter-spacing: -0.005em;
    margin: 0;
    font-weight: 600;
}
/* Разделители секций. У контейнера divider Streamlit задан отрицательный
   нижний отступ (−1rem): линия прижимается к следующему заголовку, а
   симметричные отступы «съедаются» снизу. Нейтрализуем его и задаём
   компактные равномерные отступы: пояс между секциями сокращается
   примерно с 41px до 28px, сама линия и зазоры для неё сохраняются. */
.st-key-doc_canvas [data-testid="stMarkdownContainer"]:has(hr) {
    margin-bottom: 0;
}
.st-key-doc_canvas hr {
    margin: 0.35rem 0;
}

/* Шапка документа: надзаголовок, крупный заголовок, метаданные. */
.st-key-editor_head [data-testid="stVerticalBlock"] {
    gap: 0.55rem;
}
.st-key-editor_head [data-testid="stMarkdownContainer"] p {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.16em;
    color: var(--vetai-muted);
    margin: 0;
}
.st-key-editor_head h3 {
    font-size: 40px;
    line-height: 1.12;
    letter-spacing: -0.01em;
    font-weight: 600;
    margin: 0;
}
.st-key-editor_head [data-testid="stCaptionContainer"] p {
    font-size: 15px;
    color: var(--vetai-muted);
    margin: 0;
}

/* Панель действий: компактная группа из двух кнопок с аккуратным
   вертикальным отступом от строки метаданных документа выше. */
.st-key-editor_actions {
    margin-top: 0.75rem;
}
.st-key-editor_actions [data-testid="stButton"] button {
    padding-top: 0.6rem;
    padding-bottom: 0.6rem;
}

/* Значки разделов — справа, пилюлей. */
[class*="st-key-doc_tag_"] {
    text-align: right;
}
[class*="st-key-doc_tag_"] [data-testid="stCaptionContainer"] p {
    display: inline-block;
    margin: 0;
    padding: 0.18rem 0.7rem;
    font-size: 12px;
    font-weight: 600;
    line-height: 1.3;
    color: var(--vetai-muted-strong);
    background: var(--vetai-bg);
    border: 1px solid var(--vetai-border);
    border-radius: 999px;
    white-space: nowrap;
}

/* Защищённые коммерческие разделы «Стоимость»/«Сроки»: без собственной
   рамки и внутренних отступов — текст лежит прямо на общем белом холсте
   документа, на одном горизонтальном уровне с остальными разделами.
   Нередактируемость и метки «Защищённый блок» не меняются. */
[class*="st-key-doc_locked_"] {
    background: var(--vetai-surface);
    border: none;
    padding: 0;
}
[class*="st-key-doc_locked_"] [data-testid="stMarkdownContainer"] p {
    margin: 0.2rem 0;
    font-size: 15px;
    color: var(--vetai-text);
}
[class*="st-key-doc_locked_"] [data-testid="stCaptionContainer"] p {
    margin: 0.55rem 0 0;
    font-size: 13px;
    color: var(--vetai-muted-strong);
}

/* Область прокрутки страницы фокусируется (tabIndex) и обводилась серой
   рамкой при прокрутке («Skip to main content» ставит фокус на #stMain). */
[data-testid="stMain"]:focus,
[data-testid="stMain"]:focus-visible {
    outline: none;
}
</style>
"""


def apply_theme() -> None:
    """Применить общую визуальную тему. Вызывается один раз при старте."""
    st.markdown(_CSS, unsafe_allow_html=True)

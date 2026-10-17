"""Экран «Настройки»: прайс услуг и шаблон структуры КП.

Реализует согласованный минимальный интерфейс управления прайсом и шаблоном
(REQ-26..REQ-29, OQ-02). Прайс и шаблон — доверенные данные: цены
подставляются программно (REQ-10, REQ-12), структура задаёт генерацию (REQ-07).
"""

from __future__ import annotations

import streamlit as st

from vetai.models import DEFAULT_TEMPLATE_SECTIONS, MANDATORY_SECTION_KEYS, TemplateSection
from vetai.repositories import price_repository, template_repository
from vetai.validation import format_price, parse_price_to_kopeks, validate_template_structure

_STATE_SECTIONS = "tpl_sections"
_STATE_RESET_FLAG = "_tpl_reset_requested"
_STATE_CUSTOM_SEQ = "tpl_custom_seq"


def render() -> None:
    st.header("Настройки")
    st.write(
        "Прайс услуг и шаблон структуры КП — доверенные данные проекта. "
        "Их определяет руководитель (REQ-26..REQ-28)."
    )

    prices_tab, template_tab = st.tabs(["Услуги и цены", "Шаблон КП"])
    with prices_tab:
        _render_prices()
    with template_tab:
        _render_template()


# --- Услуги и цены --------------------------------------------------------


def _render_prices() -> None:
    st.subheader("Услуги и цены")
    st.caption(
        "Цены хранятся в копейках (целыми числами) и подставляются в КП только "
        "программно — модель их не придумывает (REQ-10, REQ-12, REQ-26)."
    )

    _render_add_price_form()
    st.divider()
    _render_active_prices()
    _render_archived_prices()

    st.caption(
        "Форма брифа выбирает услуги из активных позиций прайса. Архивные "
        "позиции не предлагаются, но сохранённые брифы не изменяются."
    )


def _render_add_price_form() -> None:
    st.markdown("**Добавить услугу**")
    with st.form("price_add_form", clear_on_submit=True):
        name = st.text_input(
            "Название услуги", key="price_add_name",
            placeholder="Например: Аудит текущих процессов",
        )
        price_raw = st.text_input(
            "Цена, руб.", key="price_add_price",
            placeholder="Например: 1500 или 1500,50",
        )
        submitted = st.form_submit_button(
            "Добавить в прайс", type="primary", key="price_add_submit"
        )

    if submitted:
        try:
            price_kopeks = parse_price_to_kopeks(price_raw)
            price_repository.add_price_item(name, price_kopeks)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success(
                f"Добавлено: {name.strip()} — {format_price(price_kopeks)}"
            )


def _render_active_prices() -> None:
    items = price_repository.list_price_items()
    st.markdown("**Прайс**")
    if not items:
        st.info(
            "Прайс пуст. Добавьте услугу — она появится в форме брифа "
            "и в данных для будущей генерации."
        )
        return

    for item in items:
        with st.expander(
            f"{item.name} — {format_price(item.price_kopeks)}", expanded=False
        ):
            with st.form(f"price_edit_form_{item.id}"):
                new_name = st.text_input(
                    "Название услуги", value=item.name, key=f"price_name_{item.id}"
                )
                new_price = st.text_input(
                    "Цена, руб.",
                    value=format_price(item.price_kopeks),
                    key=f"price_value_{item.id}",
                )
                saved = st.form_submit_button(
                    "Сохранить", key=f"price_edit_submit_{item.id}"
                )
            if saved:
                try:
                    price_kopeks = parse_price_to_kopeks(new_price)
                    price_repository.update_price_item(item.id, new_name, price_kopeks)
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.success("Позиция сохранена.")

            referenced = price_repository.is_referenced_in_briefs(item.name)
            col_archive, col_delete = st.columns(2)
            with col_archive:
                if st.button(
                    "В архив", key=f"price_archive_{item.id}",
                    help="Услуга перестанет предлагаться в новых брифах.",
                ):
                    price_repository.set_archived(item.id, True)
                    st.success(
                        "Позиция перемещена в архив: в новых брифах она больше "
                        "не предлагается, а сохранённые брифы её сохраняют. "
                        "Найти её можно по флажку «Показать архив»."
                    )
            with col_delete:
                if st.button(
                    "Удалить",
                    key=f"price_delete_{item.id}",
                    disabled=referenced,
                    help=(
                        "Услуга используется в сохранённых брифах — доступно "
                        "только архивирование."
                        if referenced
                        else "Удалить позицию прайса безвозвратно."
                    ),
                ):
                    try:
                        price_repository.delete_price_item(item.id)
                    except ValueError as error:
                        st.error(str(error))
                    else:
                        st.success("Позиция удалена.")


def _render_archived_prices() -> None:
    archived = [
        item
        for item in price_repository.list_price_items(include_archived=True)
        if not item.is_active
    ]
    if not archived:
        return

    show_archived = st.checkbox("Показать архив", key="price_show_archived")
    if not show_archived:
        st.caption(
            f"Архивных позиций: {len(archived)}. Включите «Показать архив», "
            "чтобы вернуть позицию в прайс."
        )
        return
    for item in archived:
        with st.expander(
            f"{item.name} — {format_price(item.price_kopeks)} (в архиве)",
            expanded=False,
        ):
            if st.button(
                "Вернуть в прайс", key=f"price_restore_{item.id}"
            ):
                try:
                    price_repository.set_archived(item.id, False)
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.success("Позиция возвращена в прайс.")


# --- Шаблон КП ------------------------------------------------------------


def _default_section_dicts() -> list[dict[str, str]]:
    return [
        {"key": section.key, "title": section.title}
        for section in DEFAULT_TEMPLATE_SECTIONS
    ]


def _max_custom_suffix(sections: list[dict[str, str]]) -> int:
    suffixes = []
    for section in sections:
        key = section["key"]
        if key.startswith("custom_"):
            suffix = key.removeprefix("custom_")
            if suffix.isdigit():
                suffixes.append(int(suffix))
    return max(suffixes, default=0)


def _load_template_sections() -> None:
    """Загрузить структуру шаблона в состояние (до создания виджетов)."""
    try:
        template = template_repository.ensure_default_template()
    except ValueError as error:
        st.error(str(error))
        sections = _default_section_dicts()
    else:
        sections = [
            {"key": section.key, "title": section.title}
            for section in template.sections
        ]

    st.session_state[_STATE_SECTIONS] = sections
    st.session_state[_STATE_CUSTOM_SEQ] = _max_custom_suffix(sections)

    # Инициализировать значения виджетов-заголовков (можно только до их
    # создания в этом запуске) и убрать ключи удалённых разделов.
    valid_keys = {f"tpl_title_{section['key']}" for section in sections}
    for key in list(st.session_state):
        if key.startswith("tpl_title_") and key not in valid_keys:
            del st.session_state[key]
    for section in sections:
        st.session_state[f"tpl_title_{section['key']}"] = section["title"]


def _next_custom_key() -> str:
    """Монотонный идентификатор нового раздела (удалённые ключи не переиспользуются)."""
    sequence = int(st.session_state.get(_STATE_CUSTOM_SEQ, 0)) + 1
    st.session_state[_STATE_CUSTOM_SEQ] = sequence
    return f"custom_{sequence}"


def _render_template() -> None:
    st.subheader("Шаблон КП")
    st.caption(
        "Заголовки и порядок разделов редактируются. Обязательные разделы "
        "(«Описание задачи», «Состав работ и услуги», «Сроки», «Стоимость») "
        "удалить нельзя — они отмечены ниже. Разделы «О компании», «Прочие "
        "условия» и добавленные вами можно удалять. Изменения записываются в "
        "базу кнопкой «Сохранить шаблон» (REQ-07, REQ-13, REQ-27)."
    )

    if st.session_state.pop(_STATE_RESET_FLAG, False) or (
        _STATE_SECTIONS not in st.session_state
    ):
        _load_template_sections()

    sections: list[dict[str, str]] = st.session_state[_STATE_SECTIONS]

    for position, section in enumerate(sections):
        key = section["key"]
        is_mandatory = key in MANDATORY_SECTION_KEYS
        col_index, col_title, col_up, col_down, col_delete = st.columns(
            [0.5, 6, 1, 1, 1]
        )
        with col_index:
            st.markdown(str(position + 1))
        with col_title:
            st.text_input(
                "Заголовок раздела",
                key=f"tpl_title_{key}",
                label_visibility="collapsed",
            )
            if is_mandatory:
                st.caption("обязательный раздел — удалить нельзя")
        with col_up:
            if st.button(
                "↑",
                key=f"tpl_up_{key}",
                disabled=position == 0,
                help="Поднять раздел выше",
            ):
                sections[position - 1], sections[position] = (
                    sections[position],
                    sections[position - 1],
                )
                st.rerun()
        with col_down:
            if st.button(
                "↓",
                key=f"tpl_down_{key}",
                disabled=position == len(sections) - 1,
                help="Опустить раздел ниже",
            ):
                sections[position], sections[position + 1] = (
                    sections[position + 1],
                    sections[position],
                )
                st.rerun()
        with col_delete:
            if st.button(
                "✕",
                key=f"tpl_delete_{key}",
                disabled=is_mandatory,
                help=(
                    "Обязательный раздел нельзя удалить."
                    if is_mandatory
                    else "Удалить раздел из шаблона."
                ),
            ):
                sections.pop(position)
                st.rerun()

    with st.form("tpl_add_section_form", clear_on_submit=True):
        new_title = st.text_input(
            "Новый раздел", key="tpl_new_title",
            placeholder="Например: Порядок оплаты",
        )
        add_clicked = st.form_submit_button(
            "Добавить раздел", key="tpl_add_section_submit"
        )
    if add_clicked:
        title = new_title.strip()
        if not title:
            st.error("Введите заголовок раздела.")
        else:
            key = _next_custom_key()
            sections.append({"key": key, "title": title})
            # Виджет заголовка ещё не создан в этом запуске — инициализируем
            # его значение до появления (иначе сохранение увидит пустой текст).
            st.session_state[f"tpl_title_{key}"] = title
            st.rerun()

    col_save, col_reset = st.columns(2)
    with col_save:
        save_clicked = st.button("Сохранить шаблон", type="primary", key="tpl_save")
    with col_reset:
        reset_clicked = st.button("Отменить изменения", key="tpl_reset")

    if save_clicked:
        current: list[dict[str, str]] = st.session_state[_STATE_SECTIONS]
        model_sections = [
            TemplateSection(
                key=item["key"],
                title=st.session_state.get(f"tpl_title_{item['key']}", item["title"]),
                mandatory=item["key"] in MANDATORY_SECTION_KEYS,
            )
            for item in current
        ]
        errors = validate_template_structure(model_sections)
        if errors:
            st.error("Шаблон не сохранён: " + " ".join(errors))
        else:
            try:
                template = template_repository.save_sections(model_sections)
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state[_STATE_SECTIONS] = [
                    {"key": section.key, "title": section.title}
                    for section in template.sections
                ]
                st.success("Шаблон сохранён в базе.")

    if reset_clicked:
        st.session_state[_STATE_RESET_FLAG] = True
        st.rerun()

    _render_save_status()


def _current_structure() -> list[dict[str, str]]:
    """Текущая структура из состояния сессии (с учётом правок в полях).

    Заголовки нормализуются так же, как при сохранении (``strip()``), чтобы
    статус не показывал ложные «несохранённые изменения» из-за пробелов.
    """
    return [
        {
            "key": item["key"],
            "title": str(
                st.session_state.get(f"tpl_title_{item['key']}", item["title"])
            ).strip(),
        }
        for item in st.session_state.get(_STATE_SECTIONS, [])
    ]


def _saved_structure() -> list[dict[str, str]]:
    """Структура активного шаблона из базы."""
    template = template_repository.get_active_template()
    if template is None:
        return []
    return [{"key": section.key, "title": section.title} for section in template.sections]


def _render_save_status() -> None:
    """Явно показать, записаны ли правки шаблона в базу (устраняет неясность)."""
    try:
        saved = _saved_structure()
    except ValueError:
        return
    if _current_structure() != saved:
        st.info(
            "Есть несохранённые изменения: нажмите «Сохранить шаблон», чтобы "
            "записать порядок и заголовки разделов в базу. Иначе после "
            "перезагрузки страницы вернётся сохранённый вариант."
        )
    else:
        st.caption(
            "Порядок и заголовки разделов совпадают с сохранёнными в базе."
        )

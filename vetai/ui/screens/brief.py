"""Экран «Бриф».

Форма ввода данных клиента и проекта, валидация обязательных полей и
сохранение брифа в SQLite (REQ-01..REQ-05, REQ-36).
"""

from __future__ import annotations

import streamlit as st

from vetai.models import Brief
from vetai.repositories import brief_repository
from vetai.services import training_catalog
from vetai.services.training_catalog import TRAINING_CATALOG_NOTE, service_names
from vetai.validation import missing_required_labels, validate_brief

_STATE_KEYS = (
    "brief_client",
    "brief_task",
    "brief_services",
    "brief_deadlines",
    "brief_budget",
)


def ensure_state() -> None:
    """Один раз инициализировать поля формы, восстановив последний бриф.

    Восстановление после перезапуска приложения (критерий G): значения берутся
    из базы, а не теряются.
    """
    if st.session_state.get("_brief_state_initialized"):
        return

    saved = brief_repository.get_latest_brief()
    if saved is not None:
        st.session_state["brief_client"] = saved.client
        st.session_state["brief_task"] = saved.task
        st.session_state["brief_services"] = training_catalog.filter_known(
            list(saved.services)
        )
        st.session_state["brief_deadlines"] = saved.deadlines
        st.session_state["brief_budget"] = saved.budget
        st.session_state["brief_restored_id"] = saved.id
    else:
        for key in _STATE_KEYS:
            st.session_state.setdefault(key, "" if key != "brief_services" else [])

    st.session_state["_brief_state_initialized"] = True


def render() -> None:
    st.header("Бриф")
    st.write(
        "Заполните данные клиента и проекта. Поля со звёздочкой (*) обязательны: "
        "без них генерация черновика недоступна."
    )

    restored_id = st.session_state.get("brief_restored_id")
    if restored_id and not st.session_state.get("_brief_restored_notice_shown"):
        st.info(
            f"Восстановлен последний сохранённый бриф (ID {restored_id}). "
            "Можно продолжить работу."
        )
        st.session_state["_brief_restored_notice_shown"] = True

    options = service_names()

    client = st.text_input(
        "Название клиента *",
        key="brief_client",
        placeholder="Например: ООО «Пример» (учебные данные)",
    )
    task = st.text_area(
        "Описание задачи *",
        key="brief_task",
        height=140,
        placeholder="Кратко опишите задачу клиента",
    )
    services = st.multiselect(
        "Услуги * (минимум одна)",
        options=options,
        key="brief_services",
    )
    st.caption(TRAINING_CATALOG_NOTE)
    deadlines = st.text_input(
        "Сроки *",
        key="brief_deadlines",
        placeholder="Например: 30 календарных дней",
    )
    budget = st.text_input(
        "Бюджет *",
        key="brief_budget",
        placeholder="Например: 250 000 руб. (учебные данные)",
    )

    brief = Brief(
        client=client,
        task=task,
        services=list(services),
        deadlines=deadlines,
        budget=budget,
    )
    errors = validate_brief(brief)

    if errors:
        st.caption(
            "Чтобы продолжить, заполните: "
            + ", ".join(missing_required_labels(brief))
            + "."
        )

    col_save, col_generate = st.columns(2)
    with col_save:
        save_clicked = st.button("Сохранить бриф", type="primary")
    with col_generate:
        generate_clicked = st.button(
            "Сгенерировать черновик",
            disabled=bool(errors),
            help=(
                "Кнопка заблокирована, пока бриф невалиден. "
                "Генерация станет доступна на следующем этапе."
            ),
        )

    if save_clicked:
        if errors:
            st.session_state["brief_errors"] = errors
        else:
            brief_id = brief_repository.save_brief(brief)
            st.session_state["brief_errors"] = []
            st.session_state.pop("brief_restored_id", None)
            st.session_state["brief_save_flash"] = f"Бриф сохранён (ID {brief_id})."

    persisted_errors = st.session_state.get("brief_errors")
    if persisted_errors:
        st.error("Бриф не сохранён. Заполните обязательные поля:")
        for error in persisted_errors:
            st.write(f"- {error}")

    flash = st.session_state.pop("brief_save_flash", None)
    if flash:
        st.success(flash)

    if generate_clicked:
        st.info(
            "Генерация будет реализована на следующем этапе (Этап 3, REQ-06). "
            "Сейчас черновик не создаётся — экран «Черновик» сообщает свой статус."
        )

    st.divider()
    st.caption(
        "Брифы хранятся локально в базе SQLite. Используйте только обезличенные "
        "учебные данные (REQ-38)."
    )

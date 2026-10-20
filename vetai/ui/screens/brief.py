"""Экран «Бриф».

Форма ввода данных клиента и проекта, валидация обязательных полей,
сохранение брифа в SQLite и запуск генерации черновика КП (REQ-01..REQ-06,
REQ-36). Услуги выбираются из прайса (OQ-06); сохранённые брифы при изменении
прайса не переписываются. Бриф сохраняется **до** обращения к AI, чтобы при
любой ошибке провайдера данные не терялись (REQ-36).
"""

from __future__ import annotations

import streamlit as st

from vetai.ai.errors import AIProviderError
from vetai.deadlines import UNIT_LABEL_TO_KEY, UNIT_LABELS, compose_deadline, parse_deadline
from vetai.models import Brief
from vetai.repositories import brief_repository, price_repository
from vetai.services import generation
from vetai.ui import navigation
from vetai.validation import missing_required_labels, validate_brief

_STATE_KEYS = (
    "brief_client",
    "brief_task",
    "brief_services",
    "brief_budget",
)


def ensure_state() -> None:
    """Один раз инициализировать поля формы, восстановив последний бриф.

    Восстановление после перезапуска приложения (критерий G): значения берутся
    из базы, а не теряются. Услуги брифа **не фильтруются** по текущему прайсу,
    чтобы архивные/переименованные позиции не пропадали из сохранённых брифов.

    Сроки восстанавливаются как пара «значение + единица», только если единица
    распознана. Старые неоднозначные записи («30», «30 дней») не
    переинтерпретируются: показывается пометка и поля остаются пустыми (Часть Б).
    """
    if st.session_state.get("_brief_state_initialized"):
        return

    saved = brief_repository.get_latest_brief()
    if saved is not None:
        st.session_state["brief_client"] = saved.client
        st.session_state["brief_task"] = saved.task
        st.session_state["brief_services"] = list(saved.services)
        st.session_state["brief_budget"] = saved.budget
        value, unit = parse_deadline(saved.deadlines)
        if value is not None and unit is not None:
            st.session_state["brief_deadline_value"] = value
            st.session_state["brief_deadline_unit"] = UNIT_LABELS[unit]
        elif saved.deadlines.strip():
            st.session_state["brief_deadlines_legacy"] = saved.deadlines.strip()
        st.session_state["brief_restored_id"] = saved.id
    else:
        for key in _STATE_KEYS:
            st.session_state.setdefault(key, "" if key != "brief_services" else [])

    st.session_state["_brief_state_initialized"] = True


def _service_options() -> tuple[list[str], list[str]]:
    """Варианты мультивыбора услуг.

    Активные позиции прайса + услуги, уже выбранные в состоянии формы, но
    отсутствующие в активном прайсе (архивные/переименованные) — чтобы выбор
    сохранённого брифа не терялся и сам бриф не менялся.
    """
    active_names = [
        item.name for item in price_repository.list_price_items()
    ]
    active_set = set(active_names)
    kept_extra = [
        name
        for name in st.session_state.get("brief_services", [])
        if name not in active_set
    ]
    return active_names, kept_extra


def render() -> None:
    st.header("Бриф")
    st.write(
        "Заполните данные клиента и проекта. Поля со звёздочкой (*) обязательны: "
        "без них генерация черновика недоступна."
    )

    restored_id = st.session_state.get("brief_restored_id")
    if restored_id and not st.session_state.get("_brief_restored_notice_shown"):
        st.info("Восстановлен последний сохранённый бриф — можно продолжить работу.")
        st.session_state["_brief_restored_notice_shown"] = True

    active_names, kept_extra = _service_options()
    options = active_names + kept_extra

    if not active_names:
        st.info(
            "Прайс пуст: добавьте услуги и цены в разделе «Настройки» — "
            "иначе выбрать услуги нельзя."
        )

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
    if kept_extra:
        st.caption(
            "Часть выбранных услуг находится в архиве прайса: выбор сохранён, "
            "но в новых брифах эти позиции не предлагаются."
        )
    else:
        st.caption("Услуги берутся из прайса — управляется в разделе «Настройки».")
    col_value, col_unit = st.columns([1, 2])
    with col_value:
        deadline_value = st.number_input(
            "Сроки: значение *",
            key="brief_deadline_value",
            min_value=1,
            step=1,
            value=None,
            placeholder="Например: 30",
        )
    with col_unit:
        deadline_unit_label = st.selectbox(
            "Сроки: единица измерения *",
            options=list(UNIT_LABELS.values()),
            key="brief_deadline_unit",
            index=None,
            placeholder="Выберите единицу",
        )
    deadline_unit = UNIT_LABEL_TO_KEY.get(deadline_unit_label or "")

    legacy_deadlines = st.session_state.get("brief_deadlines_legacy")
    if legacy_deadlines:
        st.caption(
            f"Ранее сохранённые сроки «{legacy_deadlines}» не содержат единицы "
            "измерения. Укажите число и выберите единицу — при сохранении сроки "
            "будут записаны в виде «число + единица»."
        )

    deadlines = compose_deadline(deadline_value, deadline_unit)
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
            "Сгенерировать КП",
            disabled=bool(errors),
            help=(
                "Кнопка заблокирована, пока бриф не заполнен полностью."
                if errors
                else "Сохранить бриф и сгенерировать черновик КП."
            ),
        )
    st.caption(
        "Бриф сохраняется кнопкой «Сохранить бриф» и автоматически перед "
        "генерацией; после перезагрузки страницы форма восстанавливается."
    )

    if save_clicked:
        if errors:
            st.session_state["brief_errors"] = errors
        else:
            brief_repository.save_brief(brief)
            st.session_state["brief_errors"] = []
            st.session_state.pop("brief_restored_id", None)
            st.session_state["brief_save_flash"] = "Бриф сохранён."

    persisted_errors = st.session_state.get("brief_errors")
    if persisted_errors:
        st.error("Бриф не сохранён. Заполните обязательные поля:")
        for error in persisted_errors:
            st.write(f"- {error}")

    flash = st.session_state.pop("brief_save_flash", None)
    if flash:
        st.success(flash)

    if generate_clicked:
        _handle_generation(brief)

    st.divider()
    st.caption(
        "Брифы хранятся локально. Используйте только учебные обезличенные данные."
    )


def _handle_generation(brief: Brief) -> None:
    """Сохранить бриф и запустить генерацию черновика КП (REQ-06, REQ-36)."""
    brief_id = brief_repository.save_brief(brief)
    st.session_state["brief_errors"] = []
    st.session_state.pop("brief_restored_id", None)

    try:
        with st.spinner("Генерирую черновик КП…"):
            generation.generate_draft(brief_id)
    except AIProviderError as error:
        st.error(
            "Черновик не создан. "
            + error.user_message()
            + " Бриф сохранён — можно повторить генерацию."
        )
    except ValueError as error:
        st.error(str(error))
    else:
        st.session_state["draft_flash"] = "Коммерческое предложение подготовлено."
        st.session_state.pop("preview_version_id", None)
        st.session_state["pending_screen"] = navigation.SCREEN_DRAFT
        st.rerun()

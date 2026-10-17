"""Программная подстановка коммерческих условий (REQ-10, REQ-11, REQ-12).

Цены и сроки формируются **кодом** из доверенных данных (прайс, бриф), а не
моделью. Это ключевой контур защиты: даже если модель что-то напишет про
цены, итоговый коммерческий блок берётся только отсюда. Деньги считаются в
копейках (целые), без float (REQ-10, REQ-12).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vetai.deadlines import format_deadline, parse_deadline
from vetai.repositories import price_repository
from vetai.validation import format_price


@dataclass(frozen=True)
class CommercialItem:
    """Позиция коммерческого блока."""

    name: str
    price_kopeks: int | None  # None — для услуги нет цены в активном прайсе


@dataclass(frozen=True)
class CommercialData:
    """Доверенные коммерческие данные версии КП.

    ``total_kopeks`` равен None, если хотя бы по одной позиции нет цены:
    итог неизвестен и не выдумывается.

    Сроки хранятся одновременно как исходный текст (``deadlines_text``) и как
    разобранная пара значение/единица (``deadlines_value``, ``deadlines_unit``).
    ``deadlines_ambiguous`` — число есть, но единица не распознана: такие старые
    записи не переинтерпретируются (Часть Б, п. 2, 4).
    """

    items: list[CommercialItem]
    total_kopeks: int | None
    missing: list[str]
    deadlines_text: str
    deadlines_value: int | None = None
    deadlines_unit: str | None = None
    deadlines_ambiguous: bool = False


def build_commercial_data(
    services: list[str],
    deadlines: str,
    db_path: str | Path | None = None,
) -> CommercialData:
    """Сопоставить услуги брифа с прайсом и собрать доверенные данные.

    Цена берётся из активного прайса по названию (регистронезависимо). Если
    цены нет — позиция попадает в ``missing``, а итог не вычисляется.
    """
    active = {
        item.name.strip().casefold(): item
        for item in price_repository.list_price_items(db_path=db_path)
    }
    items: list[CommercialItem] = []
    missing: list[str] = []
    total = 0
    for name in services:
        match = active.get(name.strip().casefold())
        if match is None:
            items.append(CommercialItem(name=name, price_kopeks=None))
            missing.append(name)
        else:
            items.append(CommercialItem(name=match.name, price_kopeks=match.price_kopeks))
            total += match.price_kopeks

    deadline_value, deadline_unit = parse_deadline(deadlines or "")

    return CommercialData(
        items=items,
        total_kopeks=None if missing else total,
        missing=missing,
        deadlines_text=(deadlines or "").strip(),
        deadlines_value=deadline_value,
        deadlines_unit=deadline_unit,
        deadlines_ambiguous=deadline_value is not None and deadline_unit is None,
    )


def render_price_section(data: CommercialData) -> str:
    """Текст раздела «Стоимость» из доверенных цен (не модель)."""
    if not data.items:
        return "Перечень услуг не указан. Уточните состав работ."

    lines: list[str] = []
    for item in data.items:
        if item.price_kopeks is None:
            lines.append(f"— {item.name}: цена не указана в прайсе")
        else:
            lines.append(f"— {item.name}: {format_price(item.price_kopeks)}")

    if data.total_kopeks is None:
        lines.append(
            "Итоговая стоимость не определена: по части позиций нет цены в "
            "прайсе. Уточните прайс перед отправкой КП."
        )
    else:
        lines.append(f"Итого: {format_price(data.total_kopeks)}.")
    return "\n".join(lines)


def render_deadline_section(deadlines_text: str) -> str:
    """Текст раздела «Сроки» из брифа (не модель).

    Срок всегда показывается как «число + единица измерения». Если единица
    неоднозначна (старая запись вида «30» или «30 дней»), она **не
    присваивается**: выводится пометка «требует уточнения» (Часть Б, п. 2, 4).
    """
    value, unit = parse_deadline(deadlines_text or "")
    if value is None:
        return "Сроки выполнения не указаны — требует уточнения."
    if unit is None:
        return (
            f"Сроки выполнения: {value} — единица измерения не указана "
            "(рабочие дни / календарные дни / недели / месяцы); требует уточнения."
        )
    return f"Сроки выполнения: {format_deadline(value, unit)}."


def warnings_for(data: CommercialData) -> list[str]:
    """Предупреждения о неполных доверенных данных для экрана «Черновик»."""
    warnings: list[str] = []
    if data.missing:
        warnings.append(
            "Нет цены в активном прайсе для услуг: "
            + ", ".join(data.missing)
            + ". Итоговая стоимость не рассчитывается."
        )
    if data.deadlines_value is None:
        warnings.append(
            "В брифе не указаны сроки — раздел «Сроки» требует ручной доработки."
        )
    elif data.deadlines_ambiguous:
        warnings.append(
            "В брифе не указана единица измерения сроков (рабочие дни / "
            "календарные дни / недели / месяцы) — раздел «Сроки» требует уточнения."
        )
    return warnings


def data_from_snapshot(snapshot: dict) -> CommercialData:
    items: list[CommercialItem] = []
    for raw in snapshot.get("items", []) or []:
        if not isinstance(raw, dict):
            continue
        price = raw.get("price_kopeks")
        items.append(
            CommercialItem(name=str(raw.get("name", "")), price_kopeks=price)
        )
    deadlines_text = str(snapshot.get("deadlines", "") or "")
    value, unit = parse_deadline(deadlines_text)
    return CommercialData(
        items=items,
        total_kopeks=snapshot.get("total_kopeks"),
        missing=[str(x) for x in (snapshot.get("missing", []) or [])],
        deadlines_text=deadlines_text,
        deadlines_value=value,
        deadlines_unit=unit,
        deadlines_ambiguous=value is not None and unit is None,
    )


def expected_sections(snapshot: dict) -> dict[str, str]:
    """Ожидаемый текст коммерческих разделов из снимка доверенных данных."""
    if not snapshot:
        return {}
    data = data_from_snapshot(snapshot)
    return {
        "pricing": render_price_section(data),
        "deadlines": render_deadline_section(data.deadlines_text),
    }


def build_snapshot(data: CommercialData, deadlines_text: str) -> dict:
    return {
        "currency": "RUB",
        "items": [
            {"name": item.name, "price_kopeks": item.price_kopeks}
            for item in data.items
        ],
        "total_kopeks": data.total_kopeks,
        "missing": list(data.missing),
        "deadlines": deadlines_text,
    }

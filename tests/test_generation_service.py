"""Тесты оркестрации генерации и защитных контуров (REQ-06..REQ-13, REQ-36).

Провайдер подменяется MockProvider — реальный API не вызывается.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vetai.ai.base import GenerationRequest
from vetai.ai.errors import AIStructureError, AITimeoutError
from vetai.ai.mock_provider import MockProvider
from vetai.models import Brief, TemplateSection
from vetai.repositories import (
    brief_repository,
    generation_log_repository,
    price_repository,
    proposal_repository,
    template_repository,
)
from vetai.services import generation
from vetai.validation import format_price, parse_price_to_kopeks


def _seed_prices(db_path: Path) -> None:
    price_repository.add_price_item("Аудит", parse_price_to_kopeks("500.00"), db_path=db_path)
    price_repository.add_price_item(
        "Внедрение", parse_price_to_kopeks("1200.00"), db_path=db_path
    )


def _save_brief(db_path: Path, services: list[str] | None = None) -> int:
    return brief_repository.save_brief(
        Brief(
            client="ООО «Учебный клиент»",
            task="Внедрить решение",
            services=services if services is not None else ["Аудит", "Внедрение"],
            deadlines="30 календарных дней",
            budget="250000",
        ),
        db_path=db_path,
    )


def test_successful_generation_structure_and_sources(db_path: Path) -> None:
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)

    result = generation.generate_draft(brief_id, db_path=db_path, provider=MockProvider())

    keys = [section.key for section in result.sections]
    assert keys == ["about", "task", "scope", "deadlines", "pricing", "terms"]

    sources = {section.key: section.source for section in result.sections}
    assert sources["pricing"] == "code"
    assert sources["deadlines"] == "code"
    assert sources["task"] == "model"

    assert result.version == 1
    assert result.provider == "mock"


def test_commercial_sections_use_trusted_data(db_path: Path) -> None:
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)
    result = generation.generate_draft(brief_id, db_path=db_path, provider=MockProvider())

    pricing = next(s for s in result.sections if s.key == "pricing")
    deadlines = next(s for s in result.sections if s.key == "deadlines")

    assert format_price(50000) in pricing.text
    assert format_price(120000) in pricing.text
    assert f"Итого: {format_price(170000)}" in pricing.text
    assert deadlines.text == "Сроки выполнения: 30 календарных дней."


def test_model_cannot_override_prices(db_path: Path) -> None:
    """Даже если модель вписала цену, коммерческий раздел берётся из прайса."""
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)

    result = generation.generate_draft(
        brief_id, db_path=db_path, provider=MockProvider(risky=True)
    )

    pricing = next(s for s in result.sections if s.key == "pricing")
    assert "999 999" not in pricing.text
    # «Подозрительная» цена из текста модели попала в предупреждения, не в цены.
    assert any("999 999" in warning for warning in result.warnings)


def test_risky_promises_are_flagged(db_path: Path) -> None:
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)
    result = generation.generate_draft(
        brief_id, db_path=db_path, provider=MockProvider(risky=True)
    )
    assert any("гарантируем" in warning.lower() for warning in result.warnings)


def test_missing_price_produces_warning_and_no_total(db_path: Path) -> None:
    _seed_prices(db_path)
    brief_id = _save_brief(db_path, services=["Аудит", "Нет в прайсе"])
    result = generation.generate_draft(brief_id, db_path=db_path, provider=MockProvider())

    assert result.commercial.total_kopeks is None
    assert any("Нет цены" in warning for warning in result.warnings)
    pricing = next(s for s in result.sections if s.key == "pricing")
    assert "Итого:" not in pricing.text


def test_generation_from_modified_template(db_path: Path) -> None:
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)
    template_repository.save_sections(
        [
            TemplateSection("about", "О компании"),
            TemplateSection("task", "Описание задачи", True),
            TemplateSection("scope", "Состав работ и услуги", True),
            TemplateSection("deadlines", "Сроки", True),
            TemplateSection("pricing", "Стоимость", True),
            TemplateSection("custom_1", "Порядок оплаты"),
            TemplateSection("terms", "Прочие условия"),
        ],
        db_path=db_path,
    )

    result = generation.generate_draft(brief_id, db_path=db_path, provider=MockProvider())
    assert [s.key for s in result.sections] == [
        "about",
        "task",
        "scope",
        "deadlines",
        "pricing",
        "custom_1",
        "terms",
    ]


def test_provider_error_preserves_brief_and_logs(db_path: Path) -> None:
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)

    class FailingProvider:
        name = "failing"

        def generate(self, request: GenerationRequest) -> str:  # noqa: ARG002
            raise AITimeoutError("simulated")

    with pytest.raises(AITimeoutError):
        generation.generate_draft(brief_id, db_path=db_path, provider=FailingProvider())

    # Бриф не потерян (REQ-36), версия КП не создана.
    assert brief_repository.get_brief(brief_id, db_path=db_path) is not None
    assert proposal_repository.get_latest_draft(db_path=db_path) is None

    logs = generation_log_repository.list_logs(db_path=db_path)
    assert len(logs) == 1
    assert logs[0]["status"] == "timeout"
    assert logs[0]["provider"] == "failing"


def test_structure_error_when_response_unparsable(db_path: Path) -> None:
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)

    class GarbageProvider:
        name = "garbage"

        def generate(self, request: GenerationRequest) -> str:  # noqa: ARG002
            return "Извините, не могу сформировать ответ."

    with pytest.raises(AIStructureError):
        generation.generate_draft(brief_id, db_path=db_path, provider=GarbageProvider())

    assert proposal_repository.get_latest_draft(db_path=db_path) is None
    logs = generation_log_repository.list_logs(db_path=db_path)
    assert logs[0]["status"] == "error"


def test_logs_are_anonymized(db_path: Path) -> None:
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)
    generation.generate_draft(brief_id, db_path=db_path, provider=MockProvider())

    logs = generation_log_repository.list_logs(db_path=db_path)
    assert len(logs) == 1
    assert logs[0]["status"] == "ok"
    assert "ООО «Учебный клиент»" not in logs[0]["prompt"]
    assert "ООО «Учебный клиент»" not in logs[0]["response"]


def test_snapshot_stores_kopeks_and_deadlines(db_path: Path) -> None:
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)
    generation.generate_draft(brief_id, db_path=db_path, provider=MockProvider())

    draft = proposal_repository.get_latest_draft(db_path=db_path)
    assert draft is not None
    snapshot = draft.commercial_snapshot
    assert snapshot["currency"] == "RUB"
    assert snapshot["total_kopeks"] == 170000
    assert snapshot["deadlines"] == "30 календарных дней"


def test_unknown_brief_raises_value_error(db_path: Path) -> None:
    with pytest.raises(ValueError):
        generation.generate_draft(9999, db_path=db_path, provider=MockProvider())


def test_result_is_json_serializable(db_path: Path) -> None:
    """Тело версии сохраняется как JSON — проверяем сериализуемость."""
    _seed_prices(db_path)
    brief_id = _save_brief(db_path)
    generation.generate_draft(brief_id, db_path=db_path, provider=MockProvider())
    draft = proposal_repository.get_latest_draft(db_path=db_path)
    assert draft is not None
    # Проверяем, что snapshot читается из БД и содержит ожидаемые ключи.
    assert set(draft.commercial_snapshot) == {
        "currency",
        "items",
        "total_kopeks",
        "missing",
        "deadlines",
    }

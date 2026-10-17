"""Оркестрация генерации черновика КП.

Полный цикл (REQ-06..REQ-13):
1. бриф и активный шаблон берутся из доверенных данных;
2. коммерческий блок собирается **кодом** из прайса и брифа (REQ-10, REQ-12);
3. системный промпт + обезличенные данные передаются провайдеру (REQ-06, REQ-09);
4. ответ разбирается по разделам и валидируется по шаблону (REQ-13);
5. коммерческие разделы перезаписываются доверенными значениями;
6. результат сохраняется как версия ``generated`` (REQ-22, REQ-25);
7. промпт и ответ логируются обезличенными (REQ-30..REQ-32).

При сбое провайдера возбуждается доменная ошибка — бриф при этом уже сохранён
вызывающим кодом (REQ-36); версия КП не создаётся.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from vetai import config
from vetai.ai import get_provider
from vetai.ai.base import AIProvider, SectionSpec
from vetai.ai.errors import AIProviderError, AIStructureError
from vetai.models import (
    MODEL_SECTION_KEYS,
    SOURCE_CODE,
    SOURCE_MODEL,
    SOURCE_PLACEHOLDER,
    Brief,
    DraftSection,
    Template,
)
from vetai.repositories import (
    brief_repository,
    generation_log_repository,
    proposal_repository,
    template_repository,
)
from vetai.services import commercial, privacy, prompt_builder, text_checks

_PRICING_KEY = "pricing"
_DEADLINES_KEY = "deadlines"


@dataclass
class DraftResult:
    """Итог успешной генерации (для UI и тестов)."""

    proposal_id: int
    version_id: int
    version: int
    provider: str
    sections: list[DraftSection]
    commercial: commercial.CommercialData
    warnings: list[str]
    issues: list[str]


def generate_draft(
    brief_id: int,
    *,
    db_path: str | Path | None = None,
    provider: AIProvider | None = None,
) -> DraftResult:
    """Сгенерировать черновик КП по сохранённому брифу.

    ``provider`` можно передать явно (тесты); иначе провайдер берётся из
    конфигурации (``AI_PROVIDER``).

    Raises:
        ValueError: бриф не найден.
        AIProviderError: сбой/недоступность/пустой ответ провайдера.
        AIStructureError: ответ не удалось разобрать по разделам шаблона.
    """
    saved = brief_repository.get_brief(brief_id, db_path=db_path)
    if saved is None:
        raise ValueError("Бриф не найден — сначала сохраните бриф.")
    brief = brief_repository.to_brief(saved)

    template = _resolve_template(db_path)
    commercial_data = commercial.build_commercial_data(
        brief.services, brief.deadlines, db_path=db_path
    )
    # Модели передаются только разделы, которые она вправе заполнять по данным
    # брифа (`task`, `scope`). Коммерческие разделы подставляет код, а разделы
    # без доверенных данных вообще не отправляются (политика заземления).
    sections_spec = tuple(
        SectionSpec(key=section.key, title=section.title)
        for section in template.sections
        if section.key in MODEL_SECTION_KEYS
    )
    request = prompt_builder.build_request(brief, sections_spec)

    provider_obj = provider or get_provider()
    secrets = [config.get_gigachat_auth_key()]
    masked_prompt = privacy.mask_text(
        request.system_prompt + "\n\n" + request.user_prompt,
        client=brief.client,
        secrets=secrets,
    )

    try:
        raw = provider_obj.generate(request)
    except AIProviderError as exc:
        generation_log_repository.save_generation_log(
            provider_obj.name,
            masked_prompt,
            "",
            exc.log_status,
            None,
            db_path=db_path,
        )
        raise

    masked_response = privacy.mask_text(raw, client=brief.client, secrets=secrets)

    parsed = prompt_builder.parse_sections(raw)
    if not parsed:
        generation_log_repository.save_generation_log(
            provider_obj.name, masked_prompt, masked_response, "error", None,
            db_path=db_path,
        )
        raise AIStructureError("Разделы шаблона не распознаны в ответе.")

    sections, issues = _assemble_sections(template, parsed, commercial_data)
    warnings = commercial.warnings_for(commercial_data) + _risky_warnings(sections)

    body = _build_body(provider_obj.name, sections, warnings, issues)
    snapshot = _build_snapshot(commercial_data, brief)

    proposal_id, version_id, version = proposal_repository.append_generated_version(
        brief_id,
        json.dumps(body, ensure_ascii=False),
        json.dumps(snapshot, ensure_ascii=False),
        db_path=db_path,
    )

    generation_log_repository.save_generation_log(
        provider_obj.name, masked_prompt, masked_response, "ok", version_id,
        db_path=db_path,
    )

    return DraftResult(
        proposal_id=proposal_id,
        version_id=version_id,
        version=version,
        provider=provider_obj.name,
        sections=sections,
        commercial=commercial_data,
        warnings=warnings,
        issues=issues,
    )


def _resolve_template(db_path: str | Path | None) -> Template:
    template = template_repository.get_active_template(db_path=db_path)
    if template is None:
        template = template_repository.ensure_default_template(db_path=db_path)
    return template


def _assemble_sections(
    template: Template,
    parsed: dict[str, str],
    commercial_data: commercial.CommercialData,
) -> tuple[list[DraftSection], list[str]]:
    """Собрать разделы с учётом политики заземления (Часть А).

    - ``pricing`` / ``deadlines`` — всегда код из доверенных данных;
    - разделы из ``MODEL_SECTION_KEYS`` — текст модели, но только если он есть;
    - все прочие разделы (нет доверенных данных) — пустой текст и пометка
      «требует уточнения», модель их не заполняет.
    """
    sections: list[DraftSection] = []
    issues: list[str] = []

    for spec in template.sections:
        if spec.key == _PRICING_KEY:
            text = commercial.render_price_section(commercial_data)
            source = SOURCE_CODE
        elif spec.key == _DEADLINES_KEY:
            text = commercial.render_deadline_section(commercial_data.deadlines_text)
            source = SOURCE_CODE
        elif spec.key in MODEL_SECTION_KEYS:
            text = (parsed.get(spec.key) or "").strip()
            if text:
                source = SOURCE_MODEL
            else:
                text = ""
                source = SOURCE_PLACEHOLDER
                issues.append(
                    f"Раздел «{spec.title}» не заполнен моделью — требует уточнения."
                )
        else:
            text = ""
            source = SOURCE_PLACEHOLDER
            issues.append(
                f"Раздел «{spec.title}» требует уточнения: нет доверенных данных "
                "для его заполнения."
            )
        sections.append(
            DraftSection(key=spec.key, title=spec.title, text=text, source=source)
        )

    return sections, issues


def _risky_warnings(sections: list[DraftSection]) -> list[str]:
    """Предупреждения о «подозрительных» фразах в тексте модели (не блокирующие)."""
    warnings: list[str] = []
    for section in sections:
        if section.source != SOURCE_MODEL:
            continue
        for fragment in text_checks.find_risky_fragments(section.text):
            warnings.append(
                f"В разделе «{section.title}» возможна неподтверждённая "
                f"формулировка: «{fragment}». Проверьте вручную перед экспортом."
            )
    return warnings


def _build_body(
    provider: str,
    sections: list[DraftSection],
    warnings: list[str],
    issues: list[str],
) -> dict:
    return {
        "provider": provider,
        "sections": [
            {
                "key": section.key,
                "title": section.title,
                "text": section.text,
                "source": section.source,
            }
            for section in sections
        ],
        "warnings": warnings,
        "validation": {"issues": issues},
    }


def _build_snapshot(
    commercial_data: commercial.CommercialData, brief: Brief
) -> dict:
    return {
        "currency": "RUB",
        "items": [
            {"name": item.name, "price_kopeks": item.price_kopeks}
            for item in commercial_data.items
        ],
        "total_kopeks": commercial_data.total_kopeks,
        "missing": commercial_data.missing,
        "deadlines": brief.deadlines,
    }

"""Тесты репозитория КП и версий (REQ-22, REQ-24, REQ-25)."""

from __future__ import annotations

import json
from pathlib import Path

from vetai.models import Brief
from vetai.repositories import brief_repository, proposal_repository


def _body(provider: str, text: str) -> str:
    return json.dumps(
        {
            "provider": provider,
            "sections": [
                {"key": "task", "title": "Задача", "text": text, "source": "model"}
            ],
            "warnings": [],
            "validation": {"issues": []},
        },
        ensure_ascii=False,
    )


def _snapshot(total: int | None) -> str:
    return json.dumps({"currency": "RUB", "total_kopeks": total}, ensure_ascii=False)


def _brief_id(db_path: Path, client: str = "ООО Тест") -> int:
    return brief_repository.save_brief(
        Brief(
            client=client,
            task="Задача",
            services=["Аудит"],
            deadlines="30 дней",
            budget="100000",
        ),
        db_path=db_path,
    )


def test_latest_draft_empty_returns_none(db_path: Path) -> None:
    assert proposal_repository.get_latest_draft(db_path=db_path) is None


def test_versions_increment_for_same_brief(db_path: Path) -> None:
    brief_id = _brief_id(db_path)
    p1, v1_id, version1 = proposal_repository.append_generated_version(
        brief_id, _body("mock", "первая"), _snapshot(50000), db_path=db_path
    )
    p2, v2_id, version2 = proposal_repository.append_generated_version(
        brief_id, _body("mock", "вторая"), _snapshot(60000), db_path=db_path
    )

    assert p1 == p2
    assert (version1, version2) == (1, 2)
    assert v1_id != v2_id

    draft = proposal_repository.get_latest_draft(db_path=db_path)
    assert draft is not None
    assert draft.version == 2
    assert draft.sections[0].text == "вторая"
    assert draft.commercial_snapshot["total_kopeks"] == 60000


def test_different_briefs_create_different_proposals(db_path: Path) -> None:
    first = _brief_id(db_path, "ООО Первый")
    second = _brief_id(db_path, "ООО Второй")
    p1, _, _ = proposal_repository.append_generated_version(
        first, _body("mock", "a"), _snapshot(1), db_path=db_path
    )
    p2, _, _ = proposal_repository.append_generated_version(
        second, _body("mock", "b"), _snapshot(2), db_path=db_path
    )
    assert p1 != p2


def test_versions_listing(db_path: Path) -> None:
    brief_id = _brief_id(db_path)
    proposal_id, _, _ = proposal_repository.append_generated_version(
        brief_id, _body("mock", "1"), _snapshot(1), db_path=db_path
    )
    proposal_repository.append_generated_version(
        brief_id, _body("mock", "2"), _snapshot(2), db_path=db_path
    )
    versions = proposal_repository.list_versions(proposal_id, db_path=db_path)
    assert [v["version"] for v in versions] == [1, 2]
    assert all(v["status"] == "generated" for v in versions)

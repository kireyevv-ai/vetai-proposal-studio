"""Тесты эвристического поиска «подозрительных» фраз (REQ-11, REQ-12)."""

from __future__ import annotations

from vetai.services import text_checks


def test_detects_prices_and_promises() -> None:
    text = "Стоимость составит 100 000 руб. Мы гарантируем результат и SLA."
    found = text_checks.find_risky_fragments(text)
    assert any("руб" in fragment.lower() for fragment in found)
    assert any("гарант" in fragment.lower() for fragment in found)
    assert any("sla" in fragment.lower() for fragment in found)


def test_detects_percent_and_words() -> None:
    text = "Скидка и 100% бесплатно, штраф за просрочку."
    found = text_checks.find_risky_fragments(text)
    joined = " ".join(found).lower()
    assert "100" in joined
    assert "бесплатн" in joined
    assert "штраф" in joined


def test_clean_text_returns_nothing() -> None:
    text = "Мы подготовим и проведём аудит текущих процессов клиента."
    assert text_checks.find_risky_fragments(text) == []


def test_empty_text_returns_nothing() -> None:
    assert text_checks.find_risky_fragments("") == []


def test_duplicates_collapsed() -> None:
    found = text_checks.find_risky_fragments("гарантируем и гарантируем снова")
    assert len([f for f in found if f.lower() == "гарантируем"]) == 1


def test_detects_unconfirmed_executor_claims() -> None:
    text = (
        "Мы ведущая компания с опытом 15 лет на рынке, имеем сертификаты, "
        "награды и команду профессионалов."
    )
    found = text_checks.find_risky_fragments(text)
    joined = " ".join(found).lower()
    assert "ведущ" in joined
    assert "опыт" in joined
    assert "сертифик" in joined
    assert "команд" in joined


def test_detects_advertising_cliche() -> None:
    found = text_checks.find_risky_fragments("Реализуем проект под ключ.")
    assert any("под ключ" in fragment.lower() for fragment in found)


def test_improvement_word_is_not_a_claim() -> None:
    # «улучшение» не должно ложно срабатывать на «лучший».
    assert text_checks.find_risky_fragments("Выполним улучшение процесса.") == []

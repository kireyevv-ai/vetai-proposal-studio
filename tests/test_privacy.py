"""Тесты обезличивания для логов (REQ-31, REQ-32, REQ-34)."""

from __future__ import annotations

from vetai.services import privacy


def test_masks_email_and_phone() -> None:
    text = "Пишите на user@example.com или +7 999 123-45-67."
    masked = privacy.mask_text(text)
    assert "user@example.com" not in masked
    assert "[email]" in masked
    assert "+7 999 123-45-67" not in masked
    assert "[телефон]" in masked


def test_masks_client_name() -> None:
    masked = privacy.mask_text("Для ООО «Ромашка» подготовим КП.", client="ООО «Ромашка»")
    assert "ООО «Ромашка»" not in masked
    assert "[клиент]" in masked


def test_masks_secrets() -> None:
    masked = privacy.mask_text("token=abcd1234-secret", secrets=["abcd1234-secret"])
    assert "abcd1234-secret" not in masked
    assert "[секрет]" in masked


def test_short_secret_not_replaced() -> None:
    # Слишком короткие значения не маскируются, чтобы не портить текст целиком.
    assert privacy.mask_secrets("abc", ["abc"]) == "abc"


def test_empty_text_is_safe() -> None:
    assert privacy.mask_text("") == ""

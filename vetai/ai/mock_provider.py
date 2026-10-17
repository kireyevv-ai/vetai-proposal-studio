"""Безопасный mock-провайдер для тестов и демонстрации без внешнего API.

Позволяет проверить полный сценарий «бриф → черновик» локально: включите
``AI_PROVIDER=mock``. Провайдер ведёт себя как «дисциплинированная» модель:
возвращает разделы в ожидаемом формате, а коммерческие разделы (``pricing``,
``deadlines``) оставляет пустыми — их заполняет код из доверенных данных.
"""

from __future__ import annotations

from vetai.ai.base import GenerationRequest

_COMMERCIAL_KEYS = frozenset({"pricing", "deadlines"})


class MockProvider:
    """Детерминированный провайдер без сетевых вызовов.

    ``risky=True`` добавляет в текстовые разделы «подозрительные» цену и
    обещание — чтобы тесты проверяли, что защитные проверки их обнаруживают.
    """

    name = "mock"

    def __init__(self, risky: bool = False) -> None:
        self._risky = risky

    def generate(self, request: GenerationRequest) -> str:
        blocks: list[str] = []
        for section in request.sections:
            if section.key in _COMMERCIAL_KEYS:
                body = ""
            else:
                body = (
                    f"Черновик раздела «{section.title}» подготовлен по данным "
                    "брифа. Требуется проверка и редактирование менеджером."
                )
                if self._risky:
                    body += (
                        " Ориентировочная стоимость — 999 999 руб., "
                        "гарантируем результат в срок."
                    )
            blocks.append(f"[[SECTION: {section.key}]]\n{body}\n[[/SECTION]]")
        return "\n".join(blocks)

"""Импорт прайса из Excel (.xlsx) — REQ-47 (согласованное улучшение сверх ТЗ).

Сценарий: пользователь выбирает файл → приложение **читает и проверяет** данные,
не изменяя базу → показывает предварительный просмотр с ошибками/предупреждениями
по строкам → пользователь выбирает режим («только новые» / «новые и обновить
существующие») и подтверждает → изменения применяются **одной транзакцией**.

Правила проверок:

- обязательные колонки «Название услуги» и «Цена»; цены в файле — в рублях;
- пустые названия запрещены; отрицательные/нечисловые/с избыточной точностью
  цены запрещены;
- дубли **внутри файла** и совпадения с существующим прайсом не «уходят» молча:
  дубликаты внутри файла блокируются, существующие в режиме «только новые»
  пропускаются с пометкой, в режиме «новые и обновить» — обновляют цену;
- сопоставление названий регистронезависимое и работает с кириллицей
  (``casefold`` в Python — встроенный ``lower()`` SQLite кириллицу не сворачивает);
- деньги считаются через ``Decimal``, без float (REQ-10, REQ-12, REQ-26);
- размер файла и число строк ограничены разумным пределом;
- формулы Excel **не выполняются** (``openpyxl`` никогда их не вычисляет; читаются
  только кэшированные значения), файлы с макросами (VBA) отклоняются.

Политика сопоставления архивных услуг: сопоставление выполняется только с
**активными** позициями. Если название совпадает с услугой в архиве, строка
**пропускается** с предупреждением — импорт **не реактивирует** архив
автоматически. Услуги, отсутствующие в Excel, никогда не удаляются.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from vetai.repositories import price_repository
from vetai.validation import format_price, parse_price_to_kopeks

# --- Ограничения -------------------------------------------------------------

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 МБ — разумный предел для прайса
MAX_ROWS = 5000
ALLOWED_EXTENSIONS = (".xlsx",)

# --- Режимы импорта ----------------------------------------------------------

MODE_ADD = "add"
MODE_ADD_UPDATE = "add_update"
MODE_LABELS: dict[str, str] = {
    MODE_ADD: "Только новые услуги",
    MODE_ADD_UPDATE: "Новые и обновить существующие цены",
}

# --- Действия и статусы строк ------------------------------------------------

ACTION_ADD = "add"
ACTION_UPDATE = "update"
ACTION_SKIP = "skip"
ACTION_ERROR = "error"

STATUS_NEW = "Новая услуга"
STATUS_UPDATE = "Обновление цены"
STATUS_UNCHANGED = "Без изменений"
STATUS_SKIP_EXISTING = "Пропущено: уже в прайсе"
STATUS_SKIP_ARCHIVED = "Пропущено: услуга в архиве"
STATUS_ERROR = "Ошибка"

# --- Колонки -----------------------------------------------------------------

HEADER_NAME = "название услуги"
HEADER_PRICE = "цена"

_MONEY_UNIT_RE = re.compile(r"\s+")


# --- Модели ------------------------------------------------------------------


@dataclass
class ImportRow:
    """Строка предпросмотра импорта."""

    row_number: int
    name: str
    price_kopeks: int | None
    price_display: str
    action: str
    status: str
    message: str = ""
    match_id: int | None = None


@dataclass
class ImportPreview:
    """Результат разбора и проверки файла (база не изменяется)."""

    mode: str
    rows: list[ImportRow] = field(default_factory=list)
    new_count: int = 0
    update_count: int = 0
    skip_count: int = 0
    error_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def actionable_count(self) -> int:
        """Сколько строк будет реально записано в базу."""
        return self.new_count + self.update_count

    @property
    def has_errors(self) -> bool:
        return bool(self.errors) or self.error_count > 0


@dataclass
class ImportResult:
    """Итог применения импорта."""

    added: int
    updated: int


# --- Разбор ячеек и нормализация --------------------------------------------


def normalize_name(name: str) -> str:
    """Нормализовать название для сопоставления: пробелы + регистр, кириллица.

    ``casefold`` корректно сворачивает русские буквы (в отличие от ``lower()`` в
    SQLite), поэтому «Аудит» и «аудит» считаются одной услугой.
    """
    return _MONEY_UNIT_RE.sub(" ", (name or "").strip()).casefold()


def clean_name(value) -> str:
    """Привести ячейку названия к чистой строке (без схлопывания регистра)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return _MONEY_UNIT_RE.sub(" ", value.strip())
    if isinstance(value, bool):
        return ""
    return str(value).strip()


_MONEY_QUANT = Decimal("0.01")
_MONEY_EPSILON = Decimal("1e-9")


def _decimal_to_kopeks(value: Decimal) -> int:
    """Перевести рубли (Decimal) в копейки.

    Значения с точностью более двух знаков после запятой отклоняются — копейка
    является наименьшей денежной единицей. Исключение — артефакты двоичного
    представления double, которые Excel хранит в числовых ячейках (например
    ``0.30000000000000004`` вместо ``0.3``): такие значения округляются до
    копеек, а настоящая третья цифра (``1000.123``) остаётся ошибкой.
    """
    rounded = value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    if abs(value - rounded) > _MONEY_EPSILON:
        raise ValueError(
            "Цена указана с точностью более двух знаков после запятой."
        )
    return int(rounded * 100)


def price_to_kopeks(value) -> int | None:
    """Преобразовать значение ячейки Excel в копейки (целое).

    ``None`` — цена не указана (пустая ячейка). Формулы Excel **не выполняются**:
    ``openpyxl`` возвращает только кэшированные значения, поэтому необработанная
    формула приходит как пустая ячейка и становится ошибкой.

    Raises:
        ValueError: отрицательная, нечисловая или избыточно точная цена.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Цена должна быть числом, а не логическим значением.")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return parse_price_to_kopeks(text)  # отклоняет отрицательные и текст
    if isinstance(value, int):
        kopeks = value * 100
    elif isinstance(value, float):
        # Excel хранит числа как double; через repr переводим в Decimal и больше
        # не используем float для расчётов.
        kopeks = _decimal_to_kopeks(Decimal(repr(value)))
    elif isinstance(value, Decimal):
        kopeks = _decimal_to_kopeks(value)
    else:
        raise ValueError("Неподдерживаемый тип значения цены.")

    if kopeks < 0:
        raise ValueError("Цена не может быть отрицательной.")
    return kopeks


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


# --- Чтение файла ------------------------------------------------------------


def _check_extension(file_name: str | None) -> None:
    if not file_name:
        raise ValueError("Не указано имя файла.")
    lowered = file_name.lower()
    if not any(lowered.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise ValueError(
            "Поддерживается только формат .xlsx (книга Excel без макросов)."
        )


def _check_no_macros(data: bytes) -> None:
    """Отклонить файл с макросами (VBA) и подтвердить, что это ZIP-контейнер."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile as exc:
        raise ValueError(
            "Файл не является корректной книгой Excel (.xlsx)."
        ) from exc
    if any(name.lower().endswith("vbaproject.bin") for name in names):
        raise ValueError(
            "Файл содержит макросы (VBA) — они не поддерживаются. "
            "Сохраните книгу в формате .xlsx без макросов."
        )


def _read_rows(data: bytes) -> list[tuple[int, str, object]]:
    """Разобрать .xlsx и вернуть ``(номер строки, название, значение цены)``.

    Raises:
        ValueError: слишком большой файл, не читается книга, нет обязательных
            колонок или слишком много строк.
    """
    if len(data) > MAX_FILE_BYTES:
        limit_mb = MAX_FILE_BYTES // (1024 * 1024)
        raise ValueError(
            f"Файл слишком большой (максимум {limit_mb} МБ). "
            "Разделите прайс на несколько файлов."
        )
    _check_no_macros(data)

    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - зависимость заявлена в requirements
        raise ValueError(
            "Для импорта Excel требуется библиотека openpyxl."
        ) from exc

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(
            "Не удалось прочитать книгу Excel. Проверьте, что файл — "
            "корректный .xlsx без макросов."
        ) from exc

    try:
        sheet = workbook.active
        if sheet is None:
            raise ValueError("В книге нет листов.")

        iterator = sheet.iter_rows(values_only=True)
        name_col: int | None = None
        price_col: int | None = None
        header_row_no: int | None = None

        # Первая непустая строка — строка заголовков.
        for row_no, row in enumerate(iterator, start=1):
            if row is None or all(_is_empty(cell) for cell in row):
                continue
            for index, cell in enumerate(row):
                if isinstance(cell, str):
                    label = _MONEY_UNIT_RE.sub(" ", cell.strip()).casefold()
                    if label == HEADER_NAME:
                        name_col = index
                    elif label == HEADER_PRICE:
                        price_col = index
            if name_col is not None and price_col is not None:
                header_row_no = row_no
                break

        if header_row_no is None or name_col is None or price_col is None:
            raise ValueError(
                "В файле нет обязательных колонок «Название услуги» и «Цена». "
                "Скачайте образец и заполните его."
            )

        rows: list[tuple[int, str, object]] = []
        for row_no, row in enumerate(iterator, start=header_row_no + 1):
            if row is None:
                continue
            name_raw = row[name_col] if name_col < len(row) else None
            price_raw = row[price_col] if price_col < len(row) else None
            if _is_empty(name_raw) and _is_empty(price_raw):
                continue  # полностью пустая строка
            rows.append((row_no, clean_name(name_raw), price_raw))
            if len(rows) > MAX_ROWS:
                raise ValueError(
                    f"В файле слишком много строк (максимум {MAX_ROWS})."
                )
        return rows
    finally:
        workbook.close()


# --- Проверка и предпросмотр -------------------------------------------------


def build_preview(
    data: bytes,
    mode: str,
    db_path=None,
    file_name: str | None = None,
) -> ImportPreview:
    """Разобрать файл и подготовить предпросмотр **без изменения базы**.

    Raises:
        ValueError: фатальная ошибка файла (размер, формат, колонки, макросы).
    """
    if mode not in MODE_LABELS:
        raise ValueError("Неизвестный режим импорта.")

    if file_name:
        _check_extension(file_name)

    raw_rows = _read_rows(data)

    active = {
        normalize_name(item.name): item
        for item in price_repository.list_price_items(db_path=db_path)
    }
    archived = {
        normalize_name(item.name): item
        for item in price_repository.list_price_items(
            db_path=db_path, include_archived=True
        )
        if not item.is_active
    }

    preview = ImportPreview(mode=mode)
    seen: dict[str, int] = {}

    def _fail(row: ImportRow, message: str) -> None:
        """Добавить строку-ошибку и вынести её в видимый список ошибок."""
        preview.rows.append(
            ImportRow(
                row.row_number, row.name, None, row.price_display,
                ACTION_ERROR, STATUS_ERROR, message,
            )
        )
        preview.error_count += 1
        label = f"Строка {row.row_number}"
        if row.name:
            label += f" («{row.name}»)"
        preview.errors.append(f"{label}: {message}")

    for row_no, name, price_raw in raw_rows:
        # 1. Пустое название запрещено.
        if not name:
            _fail(
                ImportRow(row_no, "", None, "", ACTION_ERROR, STATUS_ERROR, ""),
                "Пустое название услуги.",
            )
            continue

        key = normalize_name(name)

        # 2. Цена: пустая/некорректная/отрицательная — ошибка строки.
        try:
            kopeks = price_to_kopeks(price_raw)
        except ValueError as exc:
            display = "" if _is_empty(price_raw) else str(price_raw).strip()
            _fail(
                ImportRow(row_no, name, None, display, ACTION_ERROR, STATUS_ERROR, ""),
                str(exc),
            )
            continue
        if kopeks is None:
            _fail(
                ImportRow(row_no, name, None, "", ACTION_ERROR, STATUS_ERROR, ""),
                "Не указана цена.",
            )
            continue

        # 3. Дубликат внутри файла — блокируем, чтобы не «уйти» молча.
        if key in seen:
            _fail(
                ImportRow(
                    row_no, name, kopeks, format_price(kopeks),
                    ACTION_ERROR, STATUS_ERROR, "",
                ),
                f"Дубликат: услуга «{name}» уже встречается в файле "
                f"(строка {seen[key]}).",
            )
            continue
        seen[key] = row_no

        # 4. Сопоставление с существующим прайсом.
        existing = active.get(key)
        if existing is not None:
            if mode == MODE_ADD_UPDATE:
                if existing.price_kopeks == kopeks:
                    preview.rows.append(
                        ImportRow(
                            row_no, name, kopeks, format_price(kopeks),
                            ACTION_SKIP, STATUS_UNCHANGED,
                            "Цена совпадает с текущей — изменений не требуется.",
                            match_id=existing.id,
                        )
                    )
                    preview.skip_count += 1
                else:
                    preview.rows.append(
                        ImportRow(
                            row_no, name, kopeks, format_price(kopeks),
                            ACTION_UPDATE, STATUS_UPDATE,
                            f"Цена изменится с "
                            f"{format_price(existing.price_kopeks)} "
                            f"на {format_price(kopeks)}.",
                            match_id=existing.id,
                        )
                    )
                    preview.update_count += 1
            else:  # MODE_ADD: существующие не трогаем
                preview.rows.append(
                    ImportRow(
                        row_no, name, kopeks, format_price(kopeks),
                        ACTION_SKIP, STATUS_SKIP_EXISTING,
                        "Услуга уже есть в прайсе — в режиме «только новые» "
                        "цена не обновляется.",
                        match_id=existing.id,
                    )
                )
                preview.skip_count += 1
            continue

        # 5. Архив: не реактивируем автоматически.
        if key in archived:
            archived_item = archived[key]
            preview.rows.append(
                ImportRow(
                    row_no, name, kopeks, format_price(kopeks), ACTION_SKIP,
                    STATUS_SKIP_ARCHIVED,
                    "Услуга есть в архиве прайса — импорт не реактивирует её "
                    "автоматически. Верните позицию из архива вручную, если "
                    "нужно.",
                    match_id=archived_item.id,
                )
            )
            preview.skip_count += 1
            preview.warnings.append(
                f"Строка {row_no}: услуга «{name}» есть в архиве прайса — "
                "позиция пропущена (архив не реактивируется автоматически)."
            )
            continue

        # 6. Новая услуга.
        preview.rows.append(
            ImportRow(row_no, name, kopeks, format_price(kopeks), ACTION_ADD, STATUS_NEW)
        )
        preview.new_count += 1

    return preview


# --- Применение --------------------------------------------------------------


def apply_import(preview: ImportPreview, db_path=None) -> ImportResult:
    """Применить предпросмотр одной транзакцией (частичный импорт невозможен).

    Raises:
        ValueError: конфликт/ошибка при записи; транзакция откатена, база не
            изменена.
    """
    adds = [
        (row.name, row.price_kopeks)
        for row in preview.rows
        if row.action == ACTION_ADD and row.price_kopeks is not None
    ]
    updates = [
        (row.match_id, row.price_kopeks)
        for row in preview.rows
        if row.action == ACTION_UPDATE
        and row.match_id is not None
        and row.price_kopeks is not None
    ]

    added, updated = price_repository.apply_price_import(
        adds, updates, db_path=db_path
    )
    return ImportResult(added=added, updated=updated)


# --- Образец -----------------------------------------------------------------


def build_sample_xlsx() -> bytes:
    """Пустой образец Excel: только заголовки «Название услуги» и «Цена» (руб.)."""
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "Для импорта Excel требуется библиотека openpyxl."
        ) from exc

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Прайс"
    sheet.append(["Название услуги", "Цена"])

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()

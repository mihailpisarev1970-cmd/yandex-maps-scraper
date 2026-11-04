import os
import re
from urllib.parse import urlsplit

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

from logger import logger


HEADERS = [
    "Название", "Категории", "Адрес", "Телефон",
    "Сайт", "Рейтинг", "Отзывов", "Ссылка",
]


# ---------- Нормализация для дедупликации ----------

def _normalize_name(name: str) -> str:
    if not name:
        return ""
    s = str(name).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.strip('"\'\u00ab\u00bb ')
    return s


def _normalize_site(url: str) -> str:
    if not url or str(url).strip().lower() in ("нет сайта", ""):
        return ""
    try:
        parts = urlsplit(str(url).strip())
        host = parts.netloc.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


# ---------- Загрузка существующего файла ----------

def _root_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_existing(filename: str) -> list[dict]:
    path = os.path.join(_root_dir(), filename)
    if not os.path.exists(path):
        logger.info(f"Файл {filename} не найден — начинаем с чистого листа.")
        return []

    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as e:
        logger.warning(f"Не удалось прочитать {path}: {e}")
        return []

    if not rows or len(rows) < 2:
        return []

    headers = [str(h).strip() if h is not None else "" for h in rows[0]]

    result: list[dict] = []
    for row in rows[1:]:
        item: dict = {}
        for i, h in enumerate(headers):
            if not h:
                continue
            val = row[i] if i < len(row) else None
            item[h] = "" if val is None else str(val).strip()
        if item.get("Название"):
            result.append(item)

    logger.info(f"Загружено из {filename}: {len(result)} записей")
    return result


def build_dedup_sets(items: list[dict]) -> tuple[set, set]:
    names: set[str] = set()
    sites: set[str] = set()
    for item in items:
        n = _normalize_name(item.get("Название", ""))
        if n:
            names.add(n)
        s = _normalize_site(item.get("Сайт", ""))
        if s:
            sites.add(s)
    return names, sites


def is_duplicate(org: dict, existing_names: set, existing_sites: set) -> tuple[bool, str]:
    name = _normalize_name(org.get("Название", ""))
    site = _normalize_site(org.get("Сайт", ""))

    if name and name in existing_names:
        return True, f"дубль по названию: {org.get('Название')}"

    if site and site in existing_sites:
        return True, f"дубль по сайту: {site}"

    return False, ""


# ---------- Сохранение ----------

def save_to_excel(data: list[dict], filename: str) -> str | None:
    if not data:
        logger.warning("Нет данных для сохранения.")
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = "Результаты"

    ws.append(HEADERS)

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(
        start_color="1F4E79", end_color="1F4E79", fill_type="solid"
    )

    for col_num in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for item in data:
        ws.append([item.get(h, "") for h in HEADERS])

    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            val = str(cell.value or "")
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 60)

    ws.freeze_panes = "A2"

    file_path = os.path.join(_root_dir(), filename)
    wb.save(file_path)
    logger.info(f"Сохранено: {file_path} (записей: {len(data)})")
    return file_path
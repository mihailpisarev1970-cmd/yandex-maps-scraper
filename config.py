import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _bool_env(name: str, default: str = "False") -> bool:
    return os.getenv(name, default).strip().lower() in ("true", "1", "t", "yes", "y")


class Config:
    # ===== ЗАПРОСЫ =====
    _raw_queries = os.getenv("SEARCH_QUERIES", "").strip()
    _single_query = os.getenv("SEARCH_QUERY", "Автосервис Санкт-Петербург").strip()

    if _raw_queries:
        SEARCH_QUERIES = [q.strip() for q in _raw_queries.split(";") if q.strip()]
    else:
        SEARCH_QUERIES = [_single_query]

    SEARCH_QUERY = SEARCH_QUERIES[0]

    MAX_RESULTS_PER_QUERY = int(os.getenv("MAX_RESULTS_PER_QUERY", 200))
    MAX_RESULTS = int(os.getenv("MAX_RESULTS", 0))

    QUERY_PAUSE_MIN = int(os.getenv("QUERY_PAUSE_MIN", 60))
    QUERY_PAUSE_MAX = int(os.getenv("QUERY_PAUSE_MAX", 180))

    # ===== ФАЙЛЫ =====
    EXCEL_FILENAME = os.getenv("EXCEL_FILENAME", "results.xlsx").strip()
    LOG_FILE = os.getenv("LOG_FILE", "parser.log").strip()

    # ===== БРАУЗЕР =====
    HEADLESS_MODE = _bool_env("HEADLESS_MODE", "False")

    # ===== ПРОКСИ =====
    USE_PROXY = _bool_env("USE_PROXY", "False")
    PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
    PROXY_USERNAME = os.getenv("PROXY_USERNAME", "").strip()
    PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()
    PROXY_CHECK_STRICT = _bool_env("PROXY_CHECK_STRICT", "True")

    # ===== РЕТРАИ / СОХРАНЕНИЕ =====
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    RETRY_DELAY = float(os.getenv("RETRY_DELAY", 2.0))
    SAVE_EVERY = int(os.getenv("SAVE_EVERY", 25))

    # ===== BURST =====
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 25))
    BATCH_PAUSE_MIN = int(os.getenv("BATCH_PAUSE_MIN", 150))
    BATCH_PAUSE_MAX = int(os.getenv("BATCH_PAUSE_MAX", 300))
    CARD_PAUSE_MIN = int(os.getenv("CARD_PAUSE_MIN", 1200))
    CARD_PAUSE_MAX = int(os.getenv("CARD_PAUSE_MAX", 3000))
    CAPTCHA_PAUSE = int(os.getenv("CAPTCHA_PAUSE", 900))
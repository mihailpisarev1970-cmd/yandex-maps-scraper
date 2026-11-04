import asyncio
import sys
import time

from config import Config
from logger import logger
from scraper.exporter import save_to_excel, load_existing
from scraper.proxy_check import check_proxy
from scraper.yandex_parser import parse_yandex_maps


async def main() -> int:
    start = time.time()

    logger.info("=" * 60)
    logger.info("=== Запуск парсера Яндекс.Карт ===")
    logger.info("=" * 60)
    logger.info(f"Запросов: {len(Config.SEARCH_QUERIES)}")
    for i, q in enumerate(Config.SEARCH_QUERIES, 1):
        logger.info(f"  {i}. {q}")
    logger.info(f"Лимит на запрос: {Config.MAX_RESULTS_PER_QUERY}")
    logger.info(
        f"Пачка: {Config.BATCH_SIZE} | "
        f"Пауза пачки: {Config.BATCH_PAUSE_MIN}-{Config.BATCH_PAUSE_MAX} сек | "
        f"Пауза запроса: {Config.QUERY_PAUSE_MIN}-{Config.QUERY_PAUSE_MAX} сек"
    )
    logger.info(f"Headless: {Config.HEADLESS_MODE}")
    logger.info(f"Прокси: {'включён' if Config.USE_PROXY else 'выключен'}")

    before = len(load_existing(Config.EXCEL_FILENAME))
    logger.info(f"В файле уже есть: {before} записей")

    if Config.USE_PROXY:
        if not check_proxy():
            logger.error("Прокси не работает. Останов.")
            return 1

    data = await parse_yandex_maps(
        queries=Config.SEARCH_QUERIES,
        max_per_query=Config.MAX_RESULTS_PER_QUERY,
        headless=Config.HEADLESS_MODE,
    )

    if data:
        save_to_excel(data, Config.EXCEL_FILENAME)
        added = len(data) - before
        elapsed = time.time() - start
        logger.info("=" * 60)
        logger.info(f"Готово. Всего в файле: {len(data)}")
        logger.info(f"Добавлено новых: {added}")
        logger.info(f"Время: {elapsed / 60:.1f} мин ({elapsed:.0f} сек)")
        logger.info("=" * 60)
        return 0

    logger.warning("Парсер не нашёл данных.")
    return 1


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Прервано пользователем.")
        code = 130
    sys.exit(code)
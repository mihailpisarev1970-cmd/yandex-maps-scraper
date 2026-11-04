import time
import warnings

import httpx

from config import Config
from logger import logger

warnings.filterwarnings("ignore", message="Unverified HTTPS request")


TEST_URLS = [
    "https://api.ipify.org?format=json",
    "https://ifconfig.me/ip",
    "http://api.ipify.org?format=json",
]

RETRIES = 3
RETRY_DELAY = 3.0


def _build_proxy() -> httpx.Proxy | None:
    """Собирает httpx.Proxy с корректной авторизацией."""
    if not Config.PROXY_SERVER:
        return None

    server = Config.PROXY_SERVER.strip()
    if not server.startswith(("http://", "https://")):
        server = f"http://{server}"

    if Config.PROXY_USERNAME:
        return httpx.Proxy(
            url=server,
            auth=(Config.PROXY_USERNAME, Config.PROXY_PASSWORD),
        )

    return httpx.Proxy(url=server)


def check_proxy() -> bool:
    if not Config.USE_PROXY:
        logger.info("Прокси не используется.")
        return True

    proxy = _build_proxy()
    if proxy is None:
        logger.error("USE_PROXY=True, но PROXY_SERVER пустой.")
        return not Config.PROXY_CHECK_STRICT

    logger.info(f"Проверка прокси: {proxy.url}")

    last_error = None

    for attempt in range(1, RETRIES + 1):
        for url in TEST_URLS:
            try:
                with httpx.Client(
                    proxy=proxy,
                    timeout=25.0,
                    verify=False,
                    follow_redirects=True,
                ) as client:
                    resp = client.get(url)

                    if resp.status_code != 200:
                        last_error = f"HTTP {resp.status_code} on {url}"
                        logger.warning(
                            f"[попытка {attempt}] {url} -> "
                            f"HTTP {resp.status_code}: {resp.text[:150]}"
                        )
                        continue

                    body = resp.text.strip()
                    logger.info(
                        f"Прокси OK через {url}. Ответ: {body[:200]}"
                    )
                    return True

            except httpx.ProxyError as e:
                last_error = f"ProxyError: {e}"
                logger.warning(f"[попытка {attempt}] {url} -> ProxyError: {e}")
            except httpx.ConnectError as e:
                last_error = f"ConnectError: {e}"
                logger.warning(f"[попытка {attempt}] {url} -> ConnectError: {e}")
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    f"[попытка {attempt}] {url} -> {type(e).__name__}: {e}"
                )

        if attempt < RETRIES:
            logger.info(f"Повтор через {RETRY_DELAY} сек...")
            time.sleep(RETRY_DELAY)

    logger.error(f"Прокси не работает. Последняя ошибка: {last_error}")

    if Config.PROXY_CHECK_STRICT:
        return False

    logger.warning(
        "PROXY_CHECK_STRICT=False — продолжаем несмотря на ошибку проверки."
    )
    return True
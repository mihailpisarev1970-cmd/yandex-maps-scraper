import asyncio
import random
import re
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit
from typing import Optional

from playwright.async_api import async_playwright, Page

from config import Config
from logger import logger
import selectors as S
from scraper.exporter import (
    save_to_excel,
    load_existing,
    build_dedup_sets,
    is_duplicate,
    _normalize_name,
    _normalize_site,
)


_ORG_ID_RE = re.compile(r"/maps/org/[^/]+/(\d+)")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-\(\)]{8,20}\d")

_JUNK_SITE_HOSTS = (
    "clients.site",
    "business.site",
    "yandex.ru",
    "ya.ru",
)


def _clean_url(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _is_junk_site(url: str) -> bool:
    try:
        host = urlsplit(url).netloc.lower().split(":")[0]
    except Exception:
        return False
    if host.startswith("www."):
        host = host[4:]
    return any(host == j or host.endswith("." + j) for j in _JUNK_SITE_HOSTS)


# ---------- Утилиты ----------

async def _first_text(page: Page, selectors: list[str], default: str = "") -> str:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                txt = (await loc.inner_text()).strip()
                if txt:
                    return txt
        except Exception:
            continue
    return default


async def _human_pause(min_ms: int = 1200, max_ms: int = 3000) -> None:
    delay = random.randint(min_ms, max_ms) / 1000.0
    await asyncio.sleep(delay)


async def _batch_pause() -> None:
    delay = random.randint(Config.BATCH_PAUSE_MIN, Config.BATCH_PAUSE_MAX)
    logger.info(f"Пауза между пачками: {delay} сек ({delay // 60} мин {delay % 60} сек)")
    await asyncio.sleep(delay)


async def _query_pause() -> None:
    delay = random.randint(Config.QUERY_PAUSE_MIN, Config.QUERY_PAUSE_MAX)
    logger.info(f"Пауза между запросами: {delay} сек ({delay // 60} мин {delay % 60} сек)")
    await asyncio.sleep(delay)


# ---------- Телефон ----------

def _extract_phones_from_text(text: str) -> list[str]:
    if not text:
        return []
    phones = []
    for part in re.split(r"[\n,;]+", text):
        part = part.strip()
        if not part or "показать" in part.lower():
            continue
        m = _PHONE_RE.search(part)
        if m:
            phones.append(m.group(0).strip())
    return phones


async def _collect_phone_candidates(page: Page) -> list[str]:
    raw: list[str] = []

    try:
        for el in await page.query_selector_all(S.PHONE_LINK_SELECTOR):
            try:
                txt = (await el.inner_text()).strip()
                if txt:
                    raw.append(txt)
            except Exception:
                pass
    except Exception:
        pass

    for sel in S.PHONE_TEXT_SELECTORS:
        try:
            els = await page.query_selector_all(sel)
        except Exception:
            continue
        for el in els:
            try:
                txt = (await el.inner_text()).strip()
                if txt:
                    raw.append(txt)
            except Exception:
                pass

    result: list[str] = []
    seen: set[str] = set()
    for txt in raw:
        for ph in _extract_phones_from_text(txt):
            digits = re.sub(r"\D", "", ph)
            if len(digits) < 10 or digits in seen:
                continue
            seen.add(digits)
            result.append(ph)

    return result


async def _click_show_phone(page: Page) -> bool:
    for sel in S.PHONE_BUTTON_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            try:
                await loc.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            await loc.click(timeout=3000, force=True)
            return True
        except Exception:
            continue

    try:
        btns = await page.query_selector_all('button, div[role="button"]')
        for btn in btns:
            try:
                txt = (await btn.inner_text() or "").lower()
            except Exception:
                continue
            if "показать" in txt and "телефон" in txt:
                try:
                    await btn.click(timeout=2000, force=True)
                    return True
                except Exception:
                    continue
    except Exception:
        pass

    return False


async def _extract_phone(page: Page) -> str:
    phones = await _collect_phone_candidates(page)
    if phones:
        return ", ".join(phones)

    if await _click_show_phone(page):
        await page.wait_for_timeout(1500)
        phones = await _collect_phone_candidates(page)
        if phones:
            return ", ".join(phones)

    return "Нет телефона"


# ---------- Сайт ----------

async def _extract_website(page: Page) -> str:
    for sel in S.WEBSITE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue

            href = await loc.get_attribute("href")
            text = (await loc.inner_text()).strip()

            url = None
            if href and href.startswith(("http://", "https://")):
                url = href
            elif text and text.startswith(("http://", "https://")):
                url = text
            elif text:
                url = text

            if not url:
                continue

            if _is_junk_site(url):
                logger.info(f"[SITE] отсеяли автовизитку: {url}")
                continue

            return _clean_url(url)
        except Exception:
            continue

    return "Нет сайта"


# ---------- Рейтинг / отзывы ----------

async def _extract_rating_reviews(page: Page) -> tuple[str, str]:
    text = ""
    for sel in S.RATING_BADGE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            t = (await loc.inner_text()).strip()
            if t:
                text = t
                break
        except Exception:
            continue

    if not text:
        return "Нет рейтинга", "0"

    rating = "Нет рейтинга"
    m = re.search(r"(\d+[.,]\d+)", text)
    if m:
        rating = m.group(1).replace(",", ".")

    reviews = "0"
    m = re.search(r"(\d+)\s*(?:оцен|отзыв)", text, re.IGNORECASE)
    if m:
        try:
            reviews = str(int(m.group(1)))
        except ValueError:
            pass

    return rating, reviews


# ---------- Категории ----------

async def _extract_categories(page: Page) -> str:
    for sel in S.CATEGORY_SELECTORS:
        try:
            locs = page.locator(sel)
            count = await locs.count()
            if count == 0:
                continue
            cats: list[str] = []
            for i in range(min(count, 10)):
                try:
                    txt = (await locs.nth(i).inner_text()).strip()
                except Exception:
                    continue
                txt = txt.split("\n")[0].strip()
                if not txt or len(txt) > 60 or txt in cats:
                    continue
                cats.append(txt)
            if cats:
                return ", ".join(cats[:6])
        except Exception:
            continue

    try:
        cats = await page.evaluate(
            """
            () => {
                const seen = new Set();
                const out = [];
                const clean = (t) => (t || '').trim().replace(/\\s+/g, ' ');
                const isGood = (t) => {
                    if (!t || t.length < 3 || t.length > 50) return false;
                    if (/^\\d/.test(t)) return false;
                    if (/\\d{3,}/.test(t)) return false;
                    if (t.includes(':')) return false;
                    if (t.includes('@')) return false;
                    if (/^(маршрут|карт|санкт|москв|перейти|обзор|товар|новост|фото|отзыв|особен|подробн|панорам|показать|написать|записаться|запис|реклам|справк|редактор|создать|api|мои|настройк|личн|правил|о сервис|польз|мобильн|политик|конфиденц|правообла|услови|схема)/i.test(t)) return false;
                    return true;
                };
                const directSelectors = [
                    '[class*="categor"] a',
                    '[class*="categor"] span',
                    '[class*="rubric"] a',
                    '[class*="rubric"] span',
                ];
                for (const sel of directSelectors) {
                    const nodes = document.querySelectorAll(sel);
                    for (const n of nodes) {
                        const t = clean(n.textContent);
                        if (!isGood(t) || seen.has(t)) continue;
                        seen.add(t);
                        out.push(t);
                        if (out.length >= 6) return out;
                    }
                    if (out.length) return out;
                }
                const h1 = document.querySelector('h1');
                if (h1) {
                    let node = h1;
                    for (let i = 0; i < 8 && node; i++) {
                        node = node.parentElement;
                        if (!node) break;
                        const cls = (node.className || '').toString().toLowerCase();
                        if (cls.includes('categor') || cls.includes('rubric')) {
                            const items = node.querySelectorAll('a, span');
                            for (const it of items) {
                                const t = clean(it.textContent);
                                if (!isGood(t) || seen.has(t)) continue;
                                seen.add(t);
                                out.push(t);
                                if (out.length >= 6) break;
                            }
                            if (out.length) return out;
                        }
                    }
                }
                if (h1 && h1.parentElement) {
                    const links = h1.parentElement.querySelectorAll('a');
                    for (const a of links) {
                        const t = clean(a.textContent);
                        if (!isGood(t) || seen.has(t)) continue;
                        seen.add(t);
                        out.push(t);
                        if (out.length >= 6) break;
                    }
                }
                return out;
            }
            """
        )
        if cats:
            return ", ".join(cats[:6])
    except Exception as e:
        logger.warning(f"Ошибка извлечения категорий: {e}")

    return ""


# ---------- Основная карточка ----------

async def extract_organization_data(page: Page, card_url: str = "") -> Optional[dict]:
    try:
        await page.wait_for_selector(S.CARD_READY_SELECTOR, timeout=10000)

        name = await _first_text(page, S.NAME_SELECTORS, "Нет названия")
        address = await _first_text(page, S.ADDRESS_SELECTORS, "Нет адреса")
        address = address.split("\n")[0].strip()

        phone = await _extract_phone(page)
        website = await _extract_website(page)
        rating, reviews = await _extract_rating_reviews(page)
        categories = await _extract_categories(page)

        return {
            "Название": name.strip(),
            "Категории": categories,
            "Адрес": address,
            "Телефон": phone.strip(),
            "Сайт": website.strip(),
            "Рейтинг": rating,
            "Отзывов": reviews,
            "Ссылка": card_url or page.url,
        }
    except Exception as e:
        logger.error(f"Ошибка извлечения: {e}")
        return None


# ---------- Навигация ----------

async def _goto_with_retry(page: Page, url: str, retries: int | None = None) -> bool:
    retries = retries or Config.MAX_RETRIES
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return True
        except Exception as e:
            logger.warning(f"Попытка {attempt}/{retries} не удалась: {e}")
            if attempt < retries:
                await asyncio.sleep(Config.RETRY_DELAY)
    return False


async def _close_cookie_banner(page: Page) -> None:
    for btn_text in S.COOKIE_BUTTON_TEXTS:
        try:
            btn = page.locator(f'button:has-text("{btn_text}")').first
            if await btn.count() > 0:
                await btn.click(timeout=1000)
                await page.wait_for_timeout(500)
                return
        except Exception:
            continue


async def _scroll_results_panel(page: Page) -> None:
    try:
        await page.evaluate(
            """
            (selectors) => {
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el) {
                        el.scrollTop = el.scrollHeight;
                        return;
                    }
                }
                window.scrollBy(0, 2000);
            }
            """,
            S.SCROLL_CONTAINER_SELECTORS,
        )
    except Exception:
        await page.mouse.wheel(0, 3000)


async def _detect_captcha(page: Page) -> bool:
    try:
        captcha_selectors = [
            'iframe[src*="captcha"]',
            'div[class*="captcha"]',
            'form[action*="captcha"]',
            'div[class*="Captcha"]',
            'img[src*="captcha"]',
        ]
        for sel in captcha_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    return True
            except Exception:
                continue
        url_lower = page.url.lower()
        if "captcha" in url_lower or "showcaptcha" in url_lower:
            return True
        title = (await page.title() or "").lower()
        if "подтвердите" in title or "captcha" in title:
            return True
    except Exception:
        pass
    return False


async def _handle_captcha(page: Page, current_url: str) -> bool:
    pause = Config.CAPTCHA_PAUSE
    logger.warning(f"⚠️ Капча! Пауза {pause} сек ({pause // 60} мин).")
    await asyncio.sleep(pause)
    try:
        await page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        if await _detect_captcha(page):
            logger.error("Капча не прошла после паузы.")
            return False
        logger.info("Капча пройдена, продолжаем.")
        return True
    except Exception as e:
        logger.error(f"Ошибка после паузы от капчи: {e}")
        return False


# ---------- Сбор ссылок ----------

def _normalize_org_url(href: str) -> Optional[str]:
    if not href:
        return None
    clean = href.split("?")[0].split("#")[0]
    m = _ORG_ID_RE.search(clean)
    if not m:
        return None
    main_path = clean[: m.end()] + "/"
    if main_path.startswith("http"):
        return main_path
    return urljoin(S.BASE_URL, main_path)


def _org_id_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


async def collect_org_links(page: Page, max_results: int) -> list[str]:
    links: list[str] = []
    seen_ids: set[str] = set()
    last_count = -1
    stagnant = 0

    while len(links) < max_results and stagnant < 6:
        anchors = await page.query_selector_all(S.ORG_LINK_SELECTOR)

        for a in anchors:
            href = await a.get_attribute("href")
            normalized = _normalize_org_url(href or "")
            if not normalized:
                continue
            org_id = _org_id_from_url(normalized)
            if org_id in seen_ids:
                continue
            seen_ids.add(org_id)
            links.append(normalized)
            if len(links) >= max_results:
                break

        if len(links) >= max_results:
            break

        await _scroll_results_panel(page)
        await page.wait_for_timeout(1500)

        if len(links) == last_count:
            stagnant += 1
        else:
            stagnant = 0
            last_count = len(links)

    return links[:max_results]


# ---------- Главная функция ----------

async def parse_yandex_maps(
    queries: list[str],
    max_per_query: int,
    headless: bool,
) -> list[dict]:
    """Проходит по списку запросов, дедуп по названию/сайту, append в Excel."""
    # 1. Загружаем уже сохранённые
    existing = load_existing(Config.EXCEL_FILENAME)
    seen_names, seen_sites = build_dedup_sets(existing)
    logger.info(
        f"Загружено: {len(existing)} записей "
        f"({len(seen_names)} уник. названий, {len(seen_sites)} уник. сайтов)"
    )

    all_results: list[dict] = list(existing)
    seen_ids: set[str] = set()

    proxy_config = None
    if Config.USE_PROXY and Config.PROXY_SERVER:
        server_url = Config.PROXY_SERVER.strip()
        if not server_url.startswith(("http://", "https://")):
            server_url = f"http://{server_url}"
        proxy_config = {
            "server": server_url,
            "username": Config.PROXY_USERNAME or None,
            "password": Config.PROXY_PASSWORD or None,
        }
        logger.info(f"Используем прокси: {server_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            proxy=proxy_config,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ru-RU",
        )
        page = await context.new_page()
        await page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """
        )

        try:
            # ===== ФАЗА 1: собираем ссылки по всем запросам =====
            all_links: list[str] = []

            for qi, query in enumerate(queries, 1):
                logger.info(f"=== Запрос {qi}/{len(queries)}: {query} ===")
                url = f"https://yandex.ru/maps/?text={quote_plus(query)}"

                ok = await _goto_with_retry(page, url)
                if not ok:
                    logger.error(f"Не удалось загрузить: {url}")
                    continue

                await page.wait_for_selector(S.SEARCH_ITEM_SELECTOR, timeout=20000)
                await page.wait_for_timeout(2000)
                await _close_cookie_banner(page)

                links = await collect_org_links(page, max_per_query)
                logger.info(f"Найдено ссылок по '{query}': {len(links)}")

                new_count = 0
                for link in links:
                    org_id = _org_id_from_url(link)
                    if org_id in seen_ids:
                        continue
                    seen_ids.add(org_id)
                    all_links.append(link)
                    new_count += 1

                logger.info(
                    f"Новых ссылок: {new_count} | "
                    f"всего в очереди: {len(all_links)}"
                )

                if qi < len(queries):
                    await _query_pause()

            logger.info(f"Итого уникальных ссылок: {len(all_links)}")

            if not all_links:
                logger.warning("Ссылок нет — выходим.")
                return all_results

            # ===== ФАЗА 2: обрабатываем ссылки =====
            total_batches = (len(all_links) + Config.BATCH_SIZE - 1) // Config.BATCH_SIZE
            new_added = 0
            skipped_dups = 0

            for idx, link in enumerate(all_links, 1):
                if await _detect_captcha(page):
                    recovered = await _handle_captcha(page, link)
                    if not recovered:
                        logger.error("Не удалось восстановиться после капчи.")
                        break

                logger.info(f"Сбор данных {idx}/{len(all_links)}: {link}")

                ok = await _goto_with_retry(page, link)
                if not ok:
                    logger.warning(f"Пропускаем {link} — не загрузилось.")
                    continue

                await _human_pause(Config.CARD_PAUSE_MIN, Config.CARD_PAUSE_MAX)

                org_data = await extract_organization_data(page, card_url=link)
                if not org_data:
                    continue

                # ===== ПРОВЕРКА НА ДУБЛЬ (по названию и сайту) =====
                is_dup, reason = is_duplicate(org_data, seen_names, seen_sites)
                if is_dup:
                    skipped_dups += 1
                    logger.info(f"⏭ Пропущено: {reason}")
                    continue

                all_results.append(org_data)
                new_added += 1

                # Обновляем наборы для будущих проверок
                n = _normalize_name(org_data["Название"])
                if n:
                    seen_names.add(n)
                s = _normalize_site(org_data["Сайт"])
                if s:
                    seen_sites.add(s)

                logger.info(
                    f"✅ {org_data['Название']} | "
                    f"{org_data['Телефон']} | "
                    f"рейтинг {org_data['Рейтинг']} | "
                    f"{org_data['Отзывов']} отзывов | "
                    f"сайт: {org_data['Сайт']}"
                )

                if Config.SAVE_EVERY > 0 and new_added % Config.SAVE_EVERY == 0:
                    save_to_excel(all_results, Config.EXCEL_FILENAME)
                    logger.info(
                        f"Промежуточное сохранение: {len(all_results)} записей "
                        f"(новых: {new_added}, пропущено дублей: {skipped_dups})"
                    )

                if idx % Config.BATCH_SIZE == 0 and idx < len(all_links):
                    batch_num = idx // Config.BATCH_SIZE
                    logger.info(
                        f"📦 Пачка {batch_num}/{total_batches} "
                        f"(новых: {new_added}, дублей: {skipped_dups})"
                    )
                    await _batch_pause()

            logger.info(
                f"Итог: добавлено {new_added} новых, "
                f"пропущено {skipped_dups} дублей"
            )

        except Exception as e:
            logger.exception(f"Критическая ошибка: {e}")
            try:
                await page.screenshot(path="error_trace.png")
                logger.info("Скриншот ошибки сохранён: error_trace.png")
            except Exception:
                pass
        finally:
            await browser.close()

    return all_results
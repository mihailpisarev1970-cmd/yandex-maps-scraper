"""CSS-селекторы для Яндекс.Карт."""

BASE_URL = "https://yandex.ru"

# ---------- Карточка организации ----------

NAME_SELECTORS = [
    'h1[class*="orgpage-header-view__header"]',
    'h1[class*="card-title-view__title"]',
    'h1[itemprop="name"]',
]

CARD_READY_SELECTOR = (
    'h1[class*="orgpage-header-view__header"], '
    'h1[class*="card-title-view__title"], '
    'h1[itemprop="name"]'
)

ADDRESS_SELECTORS = [
    'a[class*="business-contacts-view__address-link"]',
    'div[class*="business-contacts-view__address"]',
    'span[class*="business-contacts-view__address"]',
    '[class*="orgpage-header-view__address"]',
    'a[class*="address-link"]',
    '[itemprop="address"]',
]

# ---------- Телефон ----------

PHONE_LINK_SELECTOR = 'a[href^="tel:"]'

PHONE_BUTTON_SELECTORS = [
    'button:has-text("Показать телефон")',
    'div[role="button"]:has-text("Показать телефон")',
    '[class*="business-contacts-view__phone-button"]',
    '[class*="phone-button"]',
]

PHONE_TEXT_SELECTORS = [
    '[class*="business-contacts-view__phone"]',
    '[class*="contacts-view__phone"]',
    '[itemprop="telephone"]',
]

# ---------- Сайт ----------

WEBSITE_SELECTORS = [
    'a[class*="business-urls-view__link"]',
    'a[class*="business-urls-view__text"]',
    '[class*="business-urls-view"] a',
]

# ---------- Рейтинг / отзывы ----------

# Обёртка, внутри которой и рейтинг, и число отзывов
RATING_BADGE_SELECTORS = [
    '[class*="business-summary-rating-badge-view__rating"]',
    '[class*="business-rating-badge-view__rating"]',
    '[class*="rating-badge-view__rating"]',
    '[class*="business-summary-rating-badge-view"]',
    '[class*="business-rating-badge-view"]',
]

# ---------- Категории ----------

CATEGORY_SELECTORS = [
    '[class*="business-categories-view__category"]',
    '[class*="business-categories-view"] a',
    '[class*="orgpage-header-view__categories"] a',
    '[class*="orgpage-header-view__categories"] span',
    '[class*="rubric-list-view__link"]',
    '[class*="rubric-list-view"] a',
]

# ---------- Выдача ----------

SEARCH_ITEM_SELECTOR = 'li.search-snippet-view'
ORG_LINK_SELECTOR = 'li.search-snippet-view a[href*="/maps/org/"]'

SCROLL_CONTAINER_SELECTORS = [
    '.scroll__container',
    '.search-list-view__list',
    '[class*="search-list-view"]',
    '[class*="scroll"]',
]

COOKIE_BUTTON_TEXTS = ["Принять", "Продолжить", "Хорошо", "Понятно"]
"""Конфигурация."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SITE_NAME = os.getenv("SITE_NAME", "ФинансПресс")
SITE_TAGLINE = os.getenv("SITE_TAGLINE", "Криптовалюты, финансы и новости")
SITE_URL = os.getenv("SITE_URL", "http://localhost:5000")

AD_URL = os.getenv("AD_URL", "https://oren-change.com")
AD_TEXT = os.getenv("AD_TEXT", "Обмен криптовалют и фиата")

SECTIONS = {
    "crypto": {
        "slug": "crypto",
        "name": "Криптовалюты",
        "icon": "🪙",
        "description": "Биткоин, блокчейн, DeFi, рынок криптоактивов",
    },
    "finance": {
        "slug": "finance",
        "name": "Финансы",
        "icon": "💵",
        "description": "Экономика, рынки, инвестиции, бизнес",
    },
    "life": {
        "slug": "life",
        "name": "Общество",
        "icon": "📰",
        "description": "Новости России и мира",
    },
}

SECTION_NAMES = {k: v["name"] for k, v in SECTIONS.items()}

RSS_SOURCES = [
    {"url": "https://forklog.com/feed/", "category": "crypto", "source": "forklog", "fetch_full": False},
    {"url": "https://bits.media/rss2/", "category": "crypto", "source": "bitsmedia", "fetch_full": False},
    {"url": "https://www.vedomosti.ru/rss/news", "category": "finance", "source": "vedomosti", "fetch_full": False},
    {"url": "https://ria.ru/export/rss2/index.xml", "category": "life", "source": "ria", "fetch_full": False},
    {"url": "https://lenta.ru/rss/news", "category": "life", "source": "lenta", "fetch_full": False},
]

PARSE_INTERVAL_MINUTES = int(os.getenv("PARSE_INTERVAL_MINUTES", "120"))
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "1000"))
FETCH_FULL_ON_PARSE = os.getenv("FETCH_FULL_ON_PARSE", "false").lower() == "true"

RATES_CACHE_MINUTES = int(os.getenv("RATES_CACHE_MINUTES", "15"))
COINS = ["bitcoin", "ethereum", "tether", "the-open-network", "binancecoin"]

_db_path_raw = os.getenv("DB_PATH", str(BASE_DIR / "data" / "news.db")).strip().strip("\"'")
DB_PATH = Path(_db_path_raw)
if not DB_PATH.is_absolute():
    DB_PATH = BASE_DIR / DB_PATH
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_manual_backup_raw = os.getenv(
    "MANUAL_POSTS_BACKUP_PATH",
    str(DB_PATH.parent / "manual_posts.json"),
).strip().strip("\"'")
MANUAL_POSTS_BACKUP_PATH = Path(_manual_backup_raw)
if not MANUAL_POSTS_BACKUP_PATH.is_absolute():
    MANUAL_POSTS_BACKUP_PATH = BASE_DIR / MANUAL_POSTS_BACKUP_PATH
MANUAL_POSTS_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

def _get_admin_ids() -> set[int]:
    """Поддержка нескольких админов через запятую.
    Приоритет: ADMIN_USER_IDS=123,456,789
    Fallback: ADMIN_USER_ID=123 (обратная совместимость).
    """
    raw = os.getenv("ADMIN_USER_IDS") or os.getenv("ADMIN_USER_ID", "0")
    ids: set[int] = set()
    for token in str(raw).replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            val = int(token)
            if val > 0:
                ids.add(val)
        except (ValueError, TypeError):
            pass
    return ids

ADMIN_USER_IDS: set[int] = _get_admin_ids()

# Для обратной совместимости (если где-то импортируют старое имя)
ADMIN_USER_ID: int = next(iter(ADMIN_USER_IDS)) if ADMIN_USER_IDS else 0

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
FEED_PER_PAGE = int(os.getenv("FEED_PER_PAGE", "20"))


def get_section(slug: str) -> dict | None:
    return SECTIONS.get(slug)

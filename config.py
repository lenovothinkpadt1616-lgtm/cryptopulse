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

DB_PATH = BASE_DIR / "data" / "news.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
FEED_PER_PAGE = int(os.getenv("FEED_PER_PAGE", "20"))


def get_section(slug: str) -> dict | None:
    return SECTIONS.get(slug)
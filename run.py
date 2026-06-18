"""Запуск: сайт + бот + автопарсинг каждые 2 часа."""

import logging
import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from app import create_app
from config import HOST, PARSE_INTERVAL_MINUTES, TELEGRAM_BOT_TOKEN
from database import init_db
from parser import parse_all
from rates import refresh_rates
from telegram_bot import run_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("novosti")


def job_parse():
    logger.info("=== Scheduled parse ===")
    try:
        result = parse_all()
        logger.info("Parse done: +%d articles", result.get("added", 0))
    except Exception as e:
        logger.error("Scheduled parse failed: %s", e)


def _startup_parse():
    """Парсинг в фоне — не блокирует запуск сайта."""
    logger.info("Background parse started...")
    try:
        result = parse_all()
        logger.info("Background parse done: +%d", result.get("added", 0))
    except Exception as e:
        logger.error("Background parse failed: %s", e)


def _refresh_rates_safe():
    try:
        refresh_rates()
    except Exception as e:
        logger.error("Rates refresh failed: %s", e)


def _run_bot_safe():
    try:
        run_bot()
    except Exception as e:
        logger.error("Telegram bot failed: %s", e)


def main():
    init_db()

    threading.Thread(target=_startup_parse, daemon=True).start()
    threading.Thread(target=_refresh_rates_safe, daemon=True).start()

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        job_parse,
        "interval",
        minutes=PARSE_INTERVAL_MINUTES,
        id="parse",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Auto-parse every %d min", PARSE_INTERVAL_MINUTES)

    bot_enabled = os.getenv("ENABLE_TELEGRAM_BOT", "true").lower() not in ("0", "false", "no")

    if TELEGRAM_BOT_TOKEN and bot_enabled:
        threading.Thread(target=_run_bot_safe, daemon=True).start()
        logger.info("Telegram bot starting in background")
    elif TELEGRAM_BOT_TOKEN and not bot_enabled:
        logger.warning("ENABLE_TELEGRAM_BOT=false - bot off")
    else:
        logger.warning("No TELEGRAM_BOT_TOKEN — bot off")

    flask_app = create_app()

    port = int(os.environ.get("PORT", "10000"))
    host = os.environ.get("HOST", HOST or "0.0.0.0")

    logger.info("Starting site on %s:%d", host, port)
    print(f"\n✅ Сайт запущен: http://{host}:{port}")
    print("   Парсинг идёт в фоне, подожди 1-2 мин для новых статей\n")

    flask_app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()

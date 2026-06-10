"""Запуск: сайт + бот + автопарсинг каждые 2 часа."""

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from app import create_app
from config import HOST, PARSE_INTERVAL_MINUTES, PORT, TELEGRAM_BOT_TOKEN
from database import init_db
from parser import parse_all
from rates import refresh_rates
from telegram_bot import run_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("novosti")


def job_parse():
    logger.info("=== Scheduled parse ===")
    result = parse_all()
    logger.info("Parse done: +%d articles", result["added"])


def _startup_parse():
    """Парсинг в фоне — не блокирует запуск сайта."""
    logger.info("Background parse started...")
    try:
        r = parse_all()
        logger.info("Background parse done: +%d", r["added"])
    except Exception as e:
        logger.error("Background parse failed: %s", e)


def main():
    init_db()

    threading.Thread(target=_startup_parse, daemon=True).start()
    threading.Thread(target=refresh_rates, daemon=True).start()

    scheduler = BackgroundScheduler()
    scheduler.add_job(job_parse, "interval", minutes=PARSE_INTERVAL_MINUTES, id="parse")
    scheduler.start()
    logger.info("Auto-parse every %d min", PARSE_INTERVAL_MINUTES)

    if TELEGRAM_BOT_TOKEN:
        threading.Thread(target=run_bot, daemon=True).start()
        logger.info("Telegram bot starting in background")
    else:
        logger.warning("No TELEGRAM_BOT_TOKEN — bot off")

    flask_app = create_app()
    print(f"\n✅ Сайт запущен: http://127.0.0.1:{PORT}")
    print(f"   (парсинг идёт в фоне, подожди 1-2 мин для новых статей)\n")
    flask_app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
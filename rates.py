"""Курсы криптовалют — кэш, безопасные значения по умолчанию."""

import logging
import time
from typing import Any

import requests

from config import COINS, RATES_CACHE_MINUTES

logger = logging.getLogger("novosti.rates")

_cache: dict[str, Any] = {"data": None, "ts": 0, "loading": False}

DEFAULT_RATES = {
    "usd_rub": 0.0,
    "coins": [
        {"symbol": "BTC", "name": "Bitcoin", "usd": 0.0, "rub": 0.0, "change_24h": 0.0},
        {"symbol": "ETH", "name": "Ethereum", "usd": 0.0, "rub": 0.0, "change_24h": 0.0},
        {"symbol": "USDT", "name": "Tether", "usd": 0.0, "rub": 0.0, "change_24h": 0.0},
        {"symbol": "TON", "name": "Toncoin", "usd": 0.0, "rub": 0.0, "change_24h": 0.0},
        {"symbol": "BNB", "name": "BNB", "usd": 0.0, "rub": 0.0, "change_24h": 0.0},
    ],
    "updated": "—",
}

COIN_LABELS = {
    "bitcoin": {"symbol": "BTC", "name": "Bitcoin"},
    "ethereum": {"symbol": "ETH", "name": "Ethereum"},
    "tether": {"symbol": "USDT", "name": "Tether"},
    "the-open-network": {"symbol": "TON", "name": "Toncoin"},
    "binancecoin": {"symbol": "BNB", "name": "BNB"},
}

HEADERS = {"User-Agent": "CryptoPulse/1.0"}


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _is_cache_valid() -> bool:
    return bool(_cache["data"]) and (time.time() - _cache["ts"]) < RATES_CACHE_MINUTES * 60


def _fetch_usd_rub() -> float:
    try:
        resp = requests.get(
            "https://www.cbr-xml-daily.ru/daily_json.js",
            headers=HEADERS,
            timeout=4,
        )
        resp.raise_for_status()
        return float(resp.json()["Valute"]["USD"]["Value"])
    except Exception as e:
        logger.warning("CBR rate: %s", e)
        return 0.0


def _fetch_crypto() -> dict:
    ids = ",".join(COINS)
    url = (
        f"https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids}&vs_currencies=usd,rub&include_24hr_change=true"
    )
    resp = requests.get(url, headers=HEADERS, timeout=6)
    resp.raise_for_status()
    return resp.json()


def get_rates() -> dict[str, Any]:
    """Мгновенный ответ из кэша. Сеть — только в refresh_rates()."""
    if _cache["data"]:
        return _cache["data"]
    return {**DEFAULT_RATES, "coins": [c.copy() for c in DEFAULT_RATES["coins"]]}


def refresh_rates() -> None:
    """Фоновое обновление курсов (вызывать из run.py)."""
    try:
        usd_rub = _fetch_usd_rub()
        coins_raw = _fetch_crypto()
        coins = []
        for coin_id, label in COIN_LABELS.items():
            raw = coins_raw.get(coin_id, {})
            coins.append({
                "symbol": label["symbol"],
                "name": label["name"],
                "usd": _safe_float(raw.get("usd")),
                "rub": _safe_float(raw.get("rub")),
                "change_24h": _safe_float(raw.get("usd_24h_change")),
            })
        _cache["data"] = {
            "usd_rub": usd_rub,
            "coins": coins,
            "updated": time.strftime("%H:%M"),
        }
        _cache["ts"] = time.time()
        logger.info("Rates updated")
    except Exception as e:
        logger.warning("Rates refresh: %s", e)


def format_price(value, currency: str = "usd") -> str:
    v = _safe_float(value)
    if v <= 0:
        return "—"
    if currency == "rub":
        if v >= 1_000_000:
            return f"{v / 1_000_000:.2f}M ₽"
        if v >= 1000:
            return f"{v:,.0f} ₽".replace(",", "\u202f")
        return f"{v:.2f} ₽"
    if v >= 1000:
        return f"${v:,.0f}".replace(",", "\u202f")
    return f"${v:.2f}"


def format_change(value) -> str:
    v = _safe_float(value)
    return f"{v:+.1f}%"
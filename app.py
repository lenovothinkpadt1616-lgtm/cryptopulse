"""Flask — новостной сайт."""

import logging
import traceback
from datetime import datetime

from flask import Flask, abort, render_template, request

from config import (
    AD_TEXT,
    AD_URL,
    FEED_PER_PAGE,
    SECTIONS,
    SECRET_KEY,
    SITE_NAME,
    SITE_TAGLINE,
    get_section,
)
from database import count_articles, get_article_by_slug, get_feed, get_top_by_section, init_db
from parser import ensure_article_content
from rates import format_change, format_price, get_rates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("novosti")

app = Flask(__name__)
app.secret_key = SECRET_KEY


def format_date(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y, %H:%M")
    except Exception:
        return str(iso_str)[:16].replace("T", " ")


def format_date_short(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        if (now - dt).days == 0:
            return dt.strftime("%H:%M")
        if (now - dt).days == 1:
            return "Вчера"
        return dt.strftime("%d.%m")
    except Exception:
        return ""


app.jinja_env.filters["fmtdate"] = format_date
app.jinja_env.filters["fmtshort"] = format_date_short
app.jinja_env.filters["fmtprice"] = format_price
app.jinja_env.filters["fmtchg"] = format_change


@app.errorhandler(500)
def error_500(e):
    logger.error("500 error: %s", traceback.format_exc())
    return render_template("error.html", code=500, message="Внутренняя ошибка сервера"), 500


@app.errorhandler(404)
def error_404(e):
    return render_template("error.html", code=404, message="Страница не найдена"), 404


@app.context_processor
def inject_globals():
    try:
        rates = get_rates()
    except Exception as e:
        logger.warning("Rates in context: %s", e)
        rates = {"coins": [], "usd_rub": 0.0, "updated": "—"}

    return {
        "site_name": SITE_NAME,
        "site_tagline": SITE_TAGLINE,
        "sections": SECTIONS,
        "rates": rates,
        "ad_url": AD_URL,
        "ad_text": AD_TEXT,
        "current_slug": None,
    }


def _render_feed(category_slug: str | None, page: int):
    articles = get_feed(page=page, per_page=FEED_PER_PAGE, category_slug=category_slug)
    total = count_articles(category_slug=category_slug)
    total_pages = max(1, (total + FEED_PER_PAGE - 1) // FEED_PER_PAGE)
    section = get_section(category_slug) if category_slug else None

    return render_template(
        "feed.html",
        articles=articles,
        page=page,
        total_pages=total_pages,
        total=total,
        section=section,
        current_slug=category_slug,
    )


@app.route("/")
def home():
    page = request.args.get("page", 1, type=int)
    return render_template(
        "home.html",
        articles=get_feed(page=page, per_page=FEED_PER_PAGE),
        top_by_section=get_top_by_section(limit=4),
        page=page,
        total_pages=max(1, (count_articles() + FEED_PER_PAGE - 1) // FEED_PER_PAGE),
        total=count_articles(),
        current_slug=None,
    )


@app.route("/article/<slug>")
def article(slug: str):
    art = get_article_by_slug(slug)
    if not art:
        abort(404)

    try:
        if art.get("source") != "manual":
            art["content"] = ensure_article_content(art)
    except Exception as e:
        logger.warning("Content load %s: %s", slug, e)

    content = art.get("content") or art.get("summary") or art.get("title") or ""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [content]

    return render_template("article.html", article=art, paragraphs=paragraphs, current_slug=None)


@app.route("/<slug>")
def section_feed(slug: str):
    if slug not in SECTIONS:
        abort(404)
    page = request.args.get("page", 1, type=int)
    return _render_feed(slug, page)


@app.route("/health")
def health():
    return {"status": "ok", "articles": count_articles()}


def create_app():
    init_db()
    return app
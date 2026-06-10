"""Мульти-источниковый парсер: крипта, финансы, жизнь."""

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from config import FETCH_FULL_ON_PARSE, MAX_ARTICLES, RSS_SOURCES
from database import add_article, article_exists, trim_old_articles, update_article_content

logger = logging.getLogger("novosti.parser")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

# Селекторы для полного текста по источникам (расширены для лучшего парсинга)
CONTENT_SELECTORS = {
    "forklog": [
        "article", ".post-content", ".entry-content", ".article__content",
        ".post__text", ".content", "[itemprop='articleBody']"
    ],
    "bitsmedia": [
        "article", ".article__text", ".post__text", ".article-body",
        ".content", ".post-content", "[itemprop='articleBody']"
    ],
    "rbc": [
        "article", ".article__text", ".article__content", ".article-body",
        ".content", "[itemprop='articleBody']"
    ],
    "vedomosti": [
        "article", ".article__text", ".article-body", ".article__body",
        ".content", ".paywall-content", "[itemprop='articleBody']"
    ],
    "ria": [
        "article", ".article__body", ".article__text", ".content",
        ".text", "[itemprop='articleBody']", ".article__content"
    ],
    "lenta": [
        "article", ".topic-body__content", ".topic-body", ".content",
        ".article__text", "[itemprop='articleBody']"
    ],
    "default": [
        "article", "[itemprop='articleBody']", "main article",
        ".article", ".article-body", ".content", ".post-content", ".entry-content"
    ],
}


def _parse_date(date_str: str) -> str:
    if not date_str:
        return datetime.utcnow().isoformat()
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(date_str).isoformat()
        except Exception:
            return datetime.utcnow().isoformat()


def _extract_image(item: ElementTree.Element) -> str:
    for tag in ("enclosure",):
        el = item.find(tag)
        if el is not None and el.get("url", "").startswith("http"):
            return el.get("url", "")
    # media:content / media:thumbnail
    for child in item:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag in ("content", "thumbnail", "enclosure"):
            url = child.get("url") or child.get("href", "")
            if url.startswith("http"):
                return url
    return ""


def _extract_description(item: ElementTree.Element) -> str:
    for tag in ("description", "content:encoded", "{http://purl.org/rss/1.0/modules/content/}encoded"):
        el = item.find(tag)
        if el is not None and el.text:
            text = BeautifulSoup(el.text, "html.parser").get_text(strip=True)
            if text:
                return text[:500]
    return ""


def fetch_rss(url: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    items = []

    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        guid_el = item.find("guid")
        pub_el = item.find("pubDate") or item.find("{http://www.w3.org/2005/Atom}published")

        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        if not link and guid_el is not None:
            link = (guid_el.text or "").strip()
        pub = _parse_date(pub_el.text if pub_el is not None else "")
        image = _extract_image(item)
        desc = _extract_description(item)

        if title and link:
            items.append({
                "title": title,
                "link": link,
                "published_at": pub,
                "image_url": image,
                "summary": desc,
            })

    return items


def fetch_full_content(url: str, source: str) -> tuple[str, str]:
    """Улучшенный парсер полного текста статьи. Пытается вытащить как можно больше
    релевантного контента, убирая шум (реклама, навигация, связанные материалы)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Пробуем найти основной контейнер статьи по приоритетным селекторам
        selectors = CONTENT_SELECTORS.get(source, []) + CONTENT_SELECTORS["default"]
        body = None
        for sel in selectors:
            body = soup.select_one(sel)
            if body:
                break

        if not body:
            # Более агрессивный поиск главного контента — самый большой по тексту блок
            candidates = soup.find_all(["article", "main", "div", "section", ".content", ".text", ".article"])
            body = max(candidates, key=lambda x: len(x.get_text(strip=True)), default=None)

        if not body:
            return "", ""

        # Убираем шум (реклама, навигация, виджеты, связанные, комментарии и т.д.)
        junk_selectors = (
            "script, style, noscript, iframe, "
            ".ad, .ads, .banner, .adv, .advert, .promo, .advertisement, "
            "aside, nav, footer, header, "
            ".share, .social, .related, .recommend, .read-also, .also-read, .more, "
            ".comments, .comment, .subscribe, .newsletter, .form, "
            ".breadcrumbs, .meta, .author, .author-info, .tags, .rubric, .source, "
            "figure figcaption, .photo-credit, .copyright, .disclaimer"
        )
        for tag in body.select(junk_selectors):
            tag.decompose()

        # Собираем реальный контент (больше элементов = полнее как на настоящих сайтах)
        paragraphs = []
        for el in body.find_all(["p", "h2", "h3", "h4", "blockquote", "li"]):
            for junk in el.select(junk_selectors):
                junk.decompose()

            text = el.get_text(separator=" ", strip=True)
            low = text.lower()
            if len(text) > 28 and not any(low.startswith(p) for p in (
                "читайте также", "см. также", "подписывайтесь", "источник:", "фото:", "видео:",
                "читать далее", "подробнее", "реклама", "спецпроект", "следите за"
            )):
                paragraphs.append(text)

        # Fallback — берём почти весь оставшийся текст страницы для максимальной полноты
        if len(paragraphs) < 3:
            text = body.get_text(separator="\n\n", strip=True)
            paragraphs = [line.strip() for line in text.split("\n\n") if len(line.strip()) > 30]

        # Максимально полный текст (реалистично как на реальных новостных сайтах)
        content = "\n\n".join(paragraphs[:90])
        summary = paragraphs[0][:340] if paragraphs else ""

        return summary, content

    except Exception as e:
        logger.warning("Full content %s: %s", url, e)
        return "", ""


def parse_source(source_cfg: dict, fetch_full: bool | None = None) -> dict:
    """Парсит один RSS-источник."""
    url = source_cfg["url"]
    category = source_cfg["category"]
    source = source_cfg["source"]
    do_full = fetch_full if fetch_full is not None else source_cfg.get("fetch_full", True)

    added, skipped, errors = 0, 0, 0

    try:
        items = fetch_rss(url)
    except Exception as e:
        logger.error("RSS %s failed: %s", source, e)
        return {"source": source, "added": 0, "skipped": 0, "errors": 1, "error": str(e)}

    for item in items:
        link = item["link"]
        if article_exists(link):
            skipped += 1
            continue

        summary = item.get("summary", "")
        content = summary or item["title"]

        if do_full and FETCH_FULL_ON_PARSE:
            try:
                s, c = fetch_full_content(link, source)
                if s:
                    summary = s
                if c:
                    content = c
            except Exception:
                errors += 1

        if not summary:
            summary = item["title"][:250]
        if not content:
            content = summary

        try:
            add_article(
                title=item["title"],
                summary=summary,
                content=content,
                image_url=item.get("image_url", ""),
                category_slug=category,
                source=source,
                source_url=link,
                published_at=item.get("published_at"),
            )
            added += 1
        except Exception as e:
            logger.error("Insert %s: %s", link, e)
            errors += 1

    return {"source": source, "added": added, "skipped": skipped, "errors": errors, "rss": len(items)}


def parse_all(fetch_full: bool | None = None) -> dict:
    """Парсит все источники."""
    results = []
    total_added = 0

    for src in RSS_SOURCES:
        logger.info("Parsing %s...", src["source"])
        r = parse_source(src, fetch_full=fetch_full)
        results.append(r)
        total_added += r["added"]
        logger.info("  %s: +%d, skip %d", src["source"], r["added"], r["skipped"])

    trimmed = trim_old_articles(MAX_ARTICLES)

    return {
        "added": total_added,
        "sources": results,
        "trimmed": trimmed,
    }


def ensure_article_content(article: dict) -> str:
    content = article.get("content", "") or ""
    title_len = len(article.get("title", ""))

    # Если контент уже выглядит полноценным — возвращаем
    if content and len(content) > title_len + 120 and content.count("\n\n") >= 2:
        return content

    url = article.get("source_url")
    source = article.get("source", "")
    if url and source != "manual":
        summary, full = fetch_full_content(url, source)
        if full and len(full) > title_len + 80:
            update_article_content(article["id"], full, summary or content[:300])
            return full

    return content or article.get("title", "")
"""SQLite база данных."""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from config import DB_PATH, MANUAL_POSTS_BACKUP_PATH, SECTION_NAMES
from slugify import make_slug, unique_slug

logger = logging.getLogger("novosti.database")
MANUAL_BACKUP_FIELDS = (
    "slug",
    "title",
    "summary",
    "content",
    "image_url",
    "category",
    "category_slug",
    "source",
    "source_url",
    "published_at",
    "created_at",
    "is_active",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _all_slugs(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT slug FROM articles WHERE slug IS NOT NULL").fetchall()
    return {r[0] for r in rows}


def _generate_slug(conn: sqlite3.Connection, title: str, article_id: int | None = None) -> str:
    base = make_slug(title)
    existing = _all_slugs(conn)
    return unique_slug(base, existing, article_id)


def _read_manual_backup() -> list[dict[str, Any]]:
    if not MANUAL_POSTS_BACKUP_PATH.exists():
        return []
    try:
        data = json.loads(MANUAL_POSTS_BACKUP_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Manual backup read failed: %s", e)
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _write_manual_backup(items: list[dict[str, Any]]) -> None:
    MANUAL_POSTS_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MANUAL_POSTS_BACKUP_PATH.with_suffix(MANUAL_POSTS_BACKUP_PATH.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, MANUAL_POSTS_BACKUP_PATH)


def _backup_manual_article(article: dict[str, Any]) -> None:
    if article.get("source") != "manual":
        return

    item = {field: article.get(field) for field in MANUAL_BACKUP_FIELDS}
    if not item.get("source_url"):
        item["source_url"] = f"manual-backup-{article.get('id') or item.get('slug')}"

    items = _read_manual_backup()
    key = item.get("source_url")
    replaced = False
    for idx, existing in enumerate(items):
        if existing.get("source_url") == key:
            items[idx] = item
            replaced = True
            break
    if not replaced:
        items.append(item)

    _write_manual_backup(items)


def _restore_manual_backups(conn: sqlite3.Connection) -> int:
    restored = 0
    for item in _read_manual_backup():
        if item.get("source") != "manual" or not item.get("title"):
            continue

        source_url = item.get("source_url")
        if source_url:
            exists = conn.execute(
                "SELECT 1 FROM articles WHERE source_url = ?", (source_url,)
            ).fetchone()
            if exists:
                continue

        slug = item.get("slug") or _generate_slug(conn, item["title"])
        if conn.execute("SELECT 1 FROM articles WHERE slug = ?", (slug,)).fetchone():
            slug = _generate_slug(conn, item["title"])

        category_slug = item.get("category_slug") or "crypto"
        category = item.get("category") or SECTION_NAMES.get(category_slug, category_slug)
        created_at = item.get("created_at") or _now()
        published_at = item.get("published_at") or created_at

        conn.execute(
            """
            INSERT INTO articles
                (slug, title, summary, content, image_url, category, category_slug,
                 source, source_url, published_at, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                item.get("title", ""),
                item.get("summary", ""),
                item.get("content", "") or item.get("summary", ""),
                item.get("image_url", ""),
                category,
                category_slug,
                "manual",
                source_url,
                published_at,
                created_at,
                int(item.get("is_active", 1)),
            ),
        )
        restored += 1
    return restored


def init_db() -> None:
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                slug            TEXT UNIQUE,
                title           TEXT NOT NULL,
                summary         TEXT DEFAULT '',
                content         TEXT DEFAULT '',
                image_url       TEXT DEFAULT '',
                category        TEXT NOT NULL DEFAULT 'Криптовалюты',
                category_slug   TEXT NOT NULL DEFAULT 'crypto',
                source          TEXT DEFAULT 'parser',
                source_url      TEXT UNIQUE,
                published_at    TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                is_active       INTEGER DEFAULT 1
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pub ON articles(published_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_active ON articles(is_active)")

        cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
        if "category_slug" not in cols:
            conn.execute("ALTER TABLE articles ADD COLUMN category_slug TEXT DEFAULT 'life'")
        if "slug" not in cols:
            conn.execute("ALTER TABLE articles ADD COLUMN slug TEXT")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cat ON articles(category_slug, published_at DESC)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_slug ON articles(slug)")

        # Slug для существующих статей
        rows = conn.execute(
            "SELECT id, title, slug FROM articles WHERE slug IS NULL OR slug = ''"
        ).fetchall()
        existing = _all_slugs(conn)
        for row in rows:
            base = make_slug(row["title"])
            slug = unique_slug(base, existing, row["id"])
            conn.execute("UPDATE articles SET slug = ? WHERE id = ?", (slug, row["id"]))
            existing.add(slug)

        restored = _restore_manual_backups(conn)
        if restored:
            logger.warning("Restored %d manual articles from backup", restored)


def article_exists(source_url: str) -> bool:
    with get_db() as conn:
        return conn.execute(
            "SELECT 1 FROM articles WHERE source_url = ?", (source_url,)
        ).fetchone() is not None


def add_article(
    title: str,
    summary: str = "",
    content: str = "",
    image_url: str = "",
    category_slug: str = "crypto",
    source: str = "parser",
    source_url: str | None = None,
    published_at: str | None = None,
) -> int:
    now = _now()
    pub = published_at or now
    cat_name = SECTION_NAMES.get(category_slug, category_slug)

    article: dict[str, Any] | None = None
    with get_db() as conn:
        slug = _generate_slug(conn, title)
        cur = conn.execute(
            """
            INSERT INTO articles
                (slug, title, summary, content, image_url, category, category_slug,
                 source, source_url, published_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug, title, summary, content or summary, image_url,
                cat_name, category_slug, source, source_url, pub, now,
            ),
        )
        article_id = cur.lastrowid
        article = {
            "id": article_id,
            "slug": slug,
            "title": title,
            "summary": summary,
            "content": content or summary,
            "image_url": image_url,
            "category": cat_name,
            "category_slug": category_slug,
            "source": source,
            "source_url": source_url,
            "published_at": pub,
            "created_at": now,
            "is_active": 1,
        }

    if article and source == "manual":
        try:
            _backup_manual_article(article)
        except Exception as e:
            logger.error("Manual backup write failed: %s", e)

    return article_id


def update_article_content(article_id: int, content: str, summary: str = "") -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE articles SET content = ?, summary = COALESCE(NULLIF(?, ''), summary) WHERE id = ?",
            (content, summary, article_id),
        )


def get_article_by_slug(slug: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM articles WHERE slug = ? AND is_active = 1", (slug,)
        ).fetchone()
        return dict(row) if row else None


def get_article(article_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM articles WHERE id = ? AND is_active = 1", (article_id,)
        ).fetchone()
        return dict(row) if row else None


def get_feed(
    page: int = 1,
    per_page: int = 15,
    category_slug: str | None = None,
) -> list[dict]:
    offset = (page - 1) * per_page
    with get_db() as conn:
        if category_slug:
            rows = conn.execute(
                """
                SELECT id, slug, title, summary, image_url, category, category_slug,
                       source, published_at
                FROM articles WHERE is_active = 1 AND category_slug = ?
                ORDER BY published_at DESC LIMIT ? OFFSET ?
                """,
                (category_slug, per_page, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, slug, title, summary, image_url, category, category_slug,
                       source, published_at
                FROM articles WHERE is_active = 1
                ORDER BY published_at DESC LIMIT ? OFFSET ?
                """,
                (per_page, offset),
            ).fetchall()
        return [dict(r) for r in rows]


def get_top_by_section(limit: int = 3) -> dict[str, list]:
    result = {}
    with get_db() as conn:
        for slug in SECTION_NAMES:
            rows = conn.execute(
                """
                SELECT id, slug, title, image_url, published_at, category_slug
                FROM articles WHERE is_active = 1 AND category_slug = ?
                ORDER BY published_at DESC LIMIT ?
                """,
                (slug, limit),
            ).fetchall()
            result[slug] = [dict(r) for r in rows]
    return result


def count_articles(category_slug: str | None = None) -> int:
    with get_db() as conn:
        if category_slug:
            row = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE is_active = 1 AND category_slug = ?",
                (category_slug,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM articles WHERE is_active = 1").fetchone()
        return row[0] if row else 0


def delete_article(article_id: int) -> bool:
    with get_db() as conn:
        article = conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        cur = conn.execute(
            "UPDATE articles SET is_active = 0 WHERE id = ?", (article_id,)
        )
        changed = cur.rowcount > 0

    if changed and article and article["source"] == "manual":
        item = dict(article)
        item["is_active"] = 0
        try:
            _backup_manual_article(item)
        except Exception as e:
            logger.error("Manual backup update failed: %s", e)

    return changed


def get_recent_for_admin(limit: int = 15) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, slug, title, category_slug, source, published_at, is_active
            FROM articles ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> dict:
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE is_active = 1"
        ).fetchone()[0]
        manual = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE is_active = 1 AND source = 'manual'"
        ).fetchone()[0]
        by_cat = {}
        for slug, name in SECTION_NAMES.items():
            cnt = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE is_active = 1 AND category_slug = ?",
                (slug,),
            ).fetchone()[0]
            by_cat[slug] = cnt
        return {"total": total, "manual": manual, "parsed": total - manual, "by_cat": by_cat}


def get_storage_status() -> dict:
    backup_items = _read_manual_backup()
    return {
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "db_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "manual_backup_path": str(MANUAL_POSTS_BACKUP_PATH),
        "manual_backup_exists": MANUAL_POSTS_BACKUP_PATH.exists(),
        "manual_backup_count": len(backup_items),
    }


def trim_old_articles(max_count: int) -> int:
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        if count <= max_count:
            return 0
        excess = count - max_count
        cur = conn.execute(
            """
            DELETE FROM articles WHERE id IN (
                SELECT id FROM articles
                WHERE source != 'manual' OR source IS NULL
                ORDER BY published_at ASC LIMIT ?
            )
            """,
            (excess,),
        )
        return cur.rowcount

"""Telegram-бот: посты в раздел + своя дата."""

import asyncio
import logging
import random
import re
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import ADMIN_USER_IDS, SECTIONS, SITE_URL, TELEGRAM_BOT_TOKEN
from database import add_article, delete_article, get_article, get_recent_for_admin, get_stats
from parser import parse_all

logger = logging.getLogger("novosti.bot")

# Шаги: раздел → заголовок → текст → фото → дата
CATEGORY, TITLE, CONTENT, IMAGE, DATE = range(5)
_drafts: dict[int, dict] = {}


def is_admin(uid: int) -> bool:
    return uid in ADMIN_USER_IDS


def _section_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"{s.get('icon', '')} {s.get('name', slug)}".strip(), callback_data=f"cat_{slug}")]
        for slug, s in SECTIONS.items()
    ]
    return InlineKeyboardMarkup(buttons)


def parse_custom_date(text: str) -> str | None:
    """
    Парсит дату: ДД.ММ.ГГГГ ЧЧ:ММ или ДД.ММ.ГГГГ
    Также YYYY-MM-DD и с временем.
    Возвращает ISO строку (UTC) или None при любой ошибке.
    Никогда не бросает исключения на плохой ввод пользователя.
    """
    if not text:
        return None
    text = text.strip()
    if text.lower() in ("/now", "сейчас", "now"):
        return datetime.now(timezone.utc).isoformat()

    # Allow trailing stuff? Be strict: use full match
    patterns = [
        (r"^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})$", True, False),   # DD.MM.YYYY HH:MM
        (r"^(\d{2})\.(\d{2})\.(\d{4})$", False, False),                     # DD.MM.YYYY
        (r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})$", True, True),     # YYYY-MM-DD HH:MM
        (r"^(\d{4})-(\d{2})-(\d{2})$", False, True),                        # YYYY-MM-DD
    ]

    for pattern, has_time, ymd_first in patterns:
        m = re.match(pattern, text)
        if not m:
            continue
        g = [int(x) for x in m.groups()]

        if has_time:
            if ymd_first:
                y, mo, d, h, mi = g
            else:
                d, mo, y, h, mi = g
        else:
            if ymd_first:
                y, mo, d = g
            else:
                d, mo, y = g
            h, mi = 12, 0

        # Strict validation — any bad value -> None (no crash)
        if not (1 <= mo <= 12):
            return None
        if not (0 <= h <= 23):
            return None
        if not (0 <= mi <= 59):
            return None
        try:
            dt = datetime(y, mo, d, h, mi, tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            # e.g. 30.02 or 31.04 etc.
            return None

    return None


# ---- Команды ----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not is_admin(update.effective_user.id):
        if update.message:
            await update.message.reply_text("⛔ Только для администратора.")
        return

    await update.message.reply_text(
        "🪙 Панель CryptoPulse\n\n"
        "/post — своя новость (выбери: крипто / финансы / жизнь)\n"
        "/delete <id> — удалить\n"
        "/list — последние новости\n"
        "/parse — спарсить все источники\n"
        "/stats — статистика\n"
        "/cancel — отмена"
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not is_admin(update.effective_user.id):
        return
    s = get_stats()
    lines = [f"📊 Всего: {s['total']} (свои: {s['manual']}, парсинг: {s['parsed']})\n"]
    for slug, cnt in s["by_cat"].items():
        name = SECTIONS.get(slug, {}).get("name", slug)
        lines.append(f"  {name}: {cnt}")
    lines.append(f"\n🌐 {SITE_URL}")
    await update.message.reply_text("\n".join(lines))


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not is_admin(update.effective_user.id):
        return
    arts = get_recent_for_admin(15)
    if not arts:
        await update.message.reply_text("📭 Пусто.")
        return
    lines = []
    for a in arts:
        st = "✅" if a["is_active"] else "❌"
        src = "✍️" if a["source"] == "manual" else "📡"
        cat = SECTIONS.get(a["category_slug"], {}).get("name", "?")[:8]
        lines.append(f"{st}{src} #{a['id']} [{cat}] {a['title'][:50]}")
    await update.message.reply_text("\n".join(lines))


async def cmd_parse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("⏳ Парсинг всех источников...")
    # Offload network-heavy parsing to a thread so the bot event loop stays responsive
    result = await asyncio.to_thread(parse_all)
    lines = [f"✅ Добавлено: {result['added']}\n"]
    for s in result.get("sources", []):
        lines.append(f"  {s['source']}: +{s['added']} (skip {s['skipped']})")
    await update.message.reply_text("\n".join(lines))


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Использование: /delete <id>")
        return
    try:
        aid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID — число.")
        return
    if delete_article(aid):
        await update.message.reply_text(f"🗑 #{aid} удалена.")
    else:
        await update.message.reply_text(f"❌ #{aid} не найдена.")


# ---- Создание поста ----

async def post_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message or not is_admin(update.effective_user.id):
        return ConversationHandler.END
    _drafts[update.effective_user.id] = {}
    await update.message.reply_text(
        "📝 Новая публикация\n\nШаг 1/5 — выбери РАЗДЕЛ:",
        reply_markup=_section_keyboard(),
    )
    return CATEGORY


async def post_category_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query or not query.from_user or not is_admin(query.from_user.id):
        return ConversationHandler.END
    await query.answer()

    slug = query.data.replace("cat_", "") if query.data else "crypto"
    _drafts[query.from_user.id]["category_slug"] = slug
    name = SECTIONS.get(slug, {}).get("name", slug)

    await query.edit_message_text(
        f"Раздел: {name}\n\nШаг 2/5 — отправь ЗАГОЛОВОК.\n/cancel — отмена"
    )
    return TITLE


async def post_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message or not update.message.text:
        return ConversationHandler.END
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    _drafts[update.effective_user.id]["title"] = update.message.text.strip()
    await update.message.reply_text("Шаг 3/5 — отправь ТЕКСТ новости.")
    return CONTENT


async def post_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message or not update.message.text:
        return ConversationHandler.END
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    _drafts[update.effective_user.id]["content"] = update.message.text.strip()
    await update.message.reply_text(
        "Шаг 4/5 — ссылка на фото, отправь фото, или /skip"
    )
    return IMAGE


async def post_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    uid = update.effective_user.id
    draft = _drafts.get(uid, {})
    image_url = ""

    if update.message.text and update.message.text.strip().lower() != "/skip":
        image_url = update.message.text.strip()
    elif update.message.photo:
        photo = update.message.photo[-1]
        f = await context.bot.get_file(photo.file_id)
        image_url = f.file_path
        if image_url and not image_url.startswith("http"):
            image_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{image_url}"

    draft["image_url"] = image_url
    _drafts[uid] = draft

    await update.message.reply_text(
        "Шаг 5/5 — дата публикации:\n"
        "Формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Пример: 10.06.2026 14:30\n"
        "Или /now — текущее время"
    )
    return DATE


async def post_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message or not update.message.text:
        return ConversationHandler.END
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    uid = update.effective_user.id
    draft = _drafts.get(uid, {})
    pub = parse_custom_date(update.message.text)

    if not pub:
        await update.message.reply_text(
            "❌ Неверный формат. Пример: 10.06.2026 14:30 или /now"
        )
        return DATE

    slug = draft.get("category_slug", "crypto")
    title = draft.get("title", "Без заголовка")
    content = draft.get("content", "")
    now = datetime.now(timezone.utc).isoformat()

    try:
        # Уникальный source_url (время + случайный суффикс чтобы избежать UNIQUE конфликтов)
        source_url = f"manual-{uid}-{now}-{random.randint(1000,9999)}"

        aid = add_article(
            title=title,
            summary=content[:300],
            content=content,
            image_url=draft.get("image_url", ""),
            category_slug=slug,
            source="manual",
            source_url=source_url,
            published_at=pub,
        )

        _drafts.pop(uid, None)
        sec_name = SECTIONS.get(slug, {}).get("name", slug)

        art = get_article(aid)
        art_slug = art["slug"] if art else str(aid)

        await update.message.reply_text(
            f"✅ Опубликовано!\n\n"
            f"ID: #{aid}\n"
            f"Раздел: {sec_name}\n"
            f"Дата: {update.message.text}\n"
            f"🔗 {SITE_URL}/article/{art_slug}"
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error("Manual post failed for user %s: %s", uid, e)
        # Не удаляем draft полностью, даём шанс попробовать ещё раз или /cancel
        await update.message.reply_text(
            "❌ Не удалось опубликовать. Возможно, проблема с датой, текстом или базой.\n"
            "Попробуй ещё раз отправить дату, или /cancel и начни заново."
        )
        return DATE  # остаёмся в шаге даты, чтобы можно было повторить


async def post_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user:
        _drafts.pop(update.effective_user.id, None)
    if update.message:
        await update.message.reply_text("❌ Отменено.")
    elif update.callback_query:
        await update.callback_query.edit_message_text("❌ Отменено.")
    return ConversationHandler.END


def build_bot_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("post", post_start)],
        states={
            CATEGORY: [CallbackQueryHandler(post_category_cb, pattern=r"^cat_")],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_title)],
            CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_content)],
            IMAGE: [MessageHandler(filters.TEXT | filters.PHOTO, post_image)],
            DATE: [MessageHandler(filters.TEXT, post_date)],
        },
        fallbacks=[CommandHandler("cancel", post_cancel)],
        per_chat=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("parse", cmd_parse))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(conv)
    app.add_error_handler(bot_error)
    return app


async def bot_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict):
        logger.error(
            "Telegram token is used by another running bot instance. "
            "Stop the duplicate service/local process or set ENABLE_TELEGRAM_BOT=false there."
        )
        return
    logger.exception("Telegram bot error", exc_info=context.error)


def run_bot() -> None:
    import asyncio

    if not TELEGRAM_BOT_TOKEN or not ADMIN_USER_IDS:
        logger.warning("Telegram bot disabled")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logger.info("Telegram bot starting...")

    build_bot_app().run_polling(
        drop_pending_updates=True,
        stop_signals=None,
    )

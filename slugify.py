"""ЧПУ-ссылки: транслит заголовка → slug."""

import re

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(text: str) -> str:
    result = []
    for ch in text.lower():
        if ch in TRANSLIT:
            result.append(TRANSLIT[ch])
        elif ch.isascii() and (ch.isalnum() or ch in " -_"):
            result.append(ch)
        elif ch in " -_":
            result.append(" ")
    return "".join(result)


def make_slug(title: str, max_len: int = 70) -> str:
    """Генерирует slug из заголовка: 'В Тюмени мужчина...' → 'v-tyumeni-muzhchina'."""
    text = transliterate(title)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text.strip())
    text = re.sub(r"-+", "-", text).strip("-")

    if not text:
        text = "news"

    if len(text) > max_len:
        text = text[:max_len].rstrip("-")

    return text


def unique_slug(base: str, existing: set[str], article_id: int | None = None) -> str:
    """Уникальный slug: при коллизии добавляет -2, -3 или -{id}."""
    if base not in existing:
        return base

    for i in range(2, 100):
        candidate = f"{base}-{i}"
        if candidate not in existing:
            return candidate

    suffix = article_id or 0
    return f"{base}-{suffix}"
"""
handlers/emoji.py — Premium custom-emoji helpers.

Telegram custom emojis render as animated for Premium users and fall back
to the plain Unicode character for non-premium users — visible to EVERYONE.

Only works in messages using parse_mode="HTML".

Usage:
    from handlers.emoji import ce, get_all_ces

    ces = await get_all_ces()
    text = f"{ces['emoji_shop']} <b>فروشگاه</b>"
"""

import time

import database as db

# How long (in seconds) the in-memory emoji cache stays valid.
# Emoji config is set by admins and almost never changes, so 60 seconds is safe.
_CACHE_TTL: float = 60.0

_ces_cache: dict[str, str] | None = None
_ces_cache_expires: float = 0.0

# Slot key → fallback plain emoji (shown to non-premium users)
SLOTS: dict[str, str] = {
    "emoji_shop":    "🛍",
    "emoji_star":    "⭐",
    "emoji_fire":    "🔥",
    "emoji_diamond": "💎",
    "emoji_check":   "✅",
    "emoji_support": "🎧",
    "emoji_wallet":  "💰",
    "emoji_profile": "👤",
    "emoji_question":"\u2753",
    "emoji_lock":    "🔐",
}

# Slot key → Persian display label
SLOT_LABELS: dict[str, str] = {
    "emoji_shop":    "فروشگاه",
    "emoji_star":    "ستاره",
    "emoji_fire":    "آتش / ویژه",
    "emoji_diamond": "الماس / پریمیوم",
    "emoji_check":   "تیک / تایید",
    "emoji_support": "پشتیبانی / هدفون",
    "emoji_wallet":  "کیف پول",
    "emoji_profile": "پروفایل کاربر",
    "emoji_question":"سوال / راهنما",
    "emoji_lock":    "امنیت / قفل",
}


def ce(emoji_id: str | None, fallback: str) -> str:
    """Return an HTML <tg-emoji> tag if emoji_id is set, else the plain fallback char."""
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


async def get_all_ces() -> dict[str, str]:
    """Return rendered HTML strings for all emoji slots.

    Results are cached in-memory for ``_CACHE_TTL`` seconds so that
    repeated renders (shop menu, profile, wallet, support) do not hit
    the database on every call.  The cache is invalidated automatically
    when an admin changes an emoji setting via ``invalidate_ces_cache()``.
    """
    global _ces_cache, _ces_cache_expires

    if _ces_cache is not None and time.monotonic() < _ces_cache_expires:
        return _ces_cache

    # Single DB query for all slots instead of one query per slot.
    settings = await db.get_settings_bulk(list(SLOTS.keys()))
    result = {
        slot: ce(settings.get(slot) or None, fallback)
        for slot, fallback in SLOTS.items()
    }

    _ces_cache = result
    _ces_cache_expires = time.monotonic() + _CACHE_TTL
    return result


def invalidate_ces_cache() -> None:
    """Immediately expire the emoji cache.

    Call this after any emoji setting is saved or cleared so the next
    render reflects the change without waiting for the TTL to expire.
    """
    global _ces_cache_expires
    _ces_cache_expires = 0.0

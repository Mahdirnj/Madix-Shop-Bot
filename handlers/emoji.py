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

import database as db

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
    """
    Fetch all configured custom emoji IDs from Settings and return a dict of
    rendered HTML strings keyed by slot name.
    Falls back to the plain emoji for any slot that has not been configured yet.
    """
    result: dict[str, str] = {}
    for slot, fallback in SLOTS.items():
        emoji_id = await db.get_setting(slot)
        result[slot] = ce(emoji_id or None, fallback)
    return result

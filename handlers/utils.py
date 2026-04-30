"""
handlers/utils.py — Shared utility functions used across handler modules.
"""

import os

from telegram import Update


def get_admin_ids() -> list[int]:
    """Parse admin IDs from the ADMIN_IDS environment variable."""
    raw = os.getenv("ADMIN_IDS", "")
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


def is_admin(user_id: int) -> bool:
    """Check whether the given user_id belongs to an admin."""
    return user_id in get_admin_ids()


def admin_filter(update: Update) -> bool:
    """Return True if the update was sent by an admin."""
    user = update.effective_user
    return user is not None and is_admin(user.id)


def get_support_handle() -> str:
    """Return the support contact handle from env, with a fallback default."""
    return os.getenv("SUPPORT_HANDLE", "@YourSupportHandle")

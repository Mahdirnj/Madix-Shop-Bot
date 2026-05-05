"""
handlers/utils.py — Shared utility functions used across handler modules.
"""

import os

from telegram import Update

# In-memory cache of admin IDs loaded from the Admins DB table.
# Populated at startup and updated whenever an admin is added/removed via the panel.
_db_admin_ids: set[int] = set()


async def refresh_admin_cache() -> None:
    """Reload all admin IDs from the Admins table into the in-memory cache."""
    import database as db
    global _db_admin_ids
    admins = await db.get_all_admins()
    _db_admin_ids = {a["user_id"] for a in admins}


def get_admin_ids() -> list[int]:
    """Parse master admin IDs from the ADMIN_IDS environment variable."""
    raw = os.getenv("ADMIN_IDS", "")
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


def get_all_admin_ids() -> set[int]:
    """Return the union of ENV master admins and DB-panel admins.

    Use this anywhere you need to notify or iterate over every admin,
    regardless of how they were added.
    """
    return set(get_admin_ids()) | _db_admin_ids


def is_admin(user_id: int) -> bool:
    """Check whether user_id belongs to an admin (env masters OR DB admins)."""
    return user_id in get_admin_ids() or user_id in _db_admin_ids


def admin_filter(update: Update) -> bool:
    """Return True if the update was sent by an admin."""
    user = update.effective_user
    return user is not None and is_admin(user.id)


async def get_support_handle() -> str:
    """Return the support handle from DB, falling back to env then a default."""
    import database as db
    value = await db.get_setting("support_handle")
    if value:
        return value
    return os.getenv("SUPPORT_HANDLE", "@YourSupportHandle")

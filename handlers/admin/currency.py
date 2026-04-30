"""
handlers/admin/currency.py — Currency rate management (manual & auto).

State machine (manual branch only):
    SET_RATE: SR_VALUE → (save)
"""

import logging
import math
from typing import Optional

import httpx
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    admin_main_menu_keyboard,
    currency_rate_mode_keyboard,
    cancel_keyboard,
)
from handlers.utils import admin_filter
from handlers.admin._helpers import cancel_conversation

logger = logging.getLogger(__name__)

# ── Conversation state ───────────────────────────────────────────────────────

SR_VALUE = 20


# ── Rate display ─────────────────────────────────────────────────────────────

async def set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the rate-mode selector (manual vs auto)."""
    if not admin_filter(update):
        return
    current = await db.get_currency_rate()
    is_auto = await db.get_setting("is_auto_currency") == "1"
    mode_text = "🤖 Auto (API)" if is_auto else "✏️ Manual"
    await update.message.reply_text(
        f"💰 *Currency Rate Settings*\n\n"
        f"Current rate: *{current:,.0f} T*\n"
        f"Mode: {mode_text}\n\n"
        f"Choose an action:",
        parse_mode="Markdown",
        reply_markup=currency_rate_mode_keyboard(),
    )


# ── Manual branch ────────────────────────────────────────────────────────────

async def rate_manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin chose Manual Update — start the manual-entry conversation."""
    query = update.callback_query
    await query.answer()
    await db.set_setting("is_auto_currency", "0")
    current = await db.get_currency_rate()
    await query.message.reply_text(
        f"✏️ *Manual Update*\n\nCurrent rate: *{current:,.0f} T*\n\nEnter the new rate (Toman per 1 foreign currency unit):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return SR_VALUE


async def sr_get_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    try:
        rate = float(update.message.text.strip().replace(",", ""))
        if rate < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid number. Enter a positive number:")
        return SR_VALUE
    await db.set_setting("currency_rate", str(rate))
    await update.message.reply_text(
        f"✅ Currency rate updated to *{rate:,.2f} T*.",
        parse_mode="Markdown",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ── Auto branch ──────────────────────────────────────────────────────────────

async def rate_auto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin chose Auto Update — enable the flag and immediately fetch once."""
    query = update.callback_query
    await query.answer()
    await db.set_setting("is_auto_currency", "1")
    rate = await _fetch_and_save_rate()
    if rate:
        await query.edit_message_text(
            f"✅ Auto-update *enabled*.\nRate fetched from API: *{rate:,} T*\n"
            f"_(Updates every 3 hours)_",
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            "❌ Auto-update enabled, but the initial API fetch *failed*. "
            "The rate will be retried on the next scheduled run (3 h).",
            parse_mode="Markdown",
        )


async def _fetch_and_save_rate() -> Optional[int]:
    """
    Fetch USDT/RLS mark price from Nobitex, convert Rials → Tomans,
    round UP to the nearest 1,000 T, and persist in Settings.
    Returns the saved Toman value, or None on failure.
    """
    url = "https://apiv2.nobitex.ir/market/stats?srcCurrency=usdt&dstCurrency=rls"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        mark_price_str = data["stats"]["usdt-rls"]["mark"]
        rial_price = float(mark_price_str)
        toman_price = rial_price / 10
        rounded = math.ceil(toman_price / 1000) * 1000
        await db.set_setting("currency_rate", str(rounded))
        logger.info("Auto currency rate updated: %s T", rounded)
        return rounded
    except Exception as exc:
        logger.error("Failed to fetch currency rate: %s", exc)
        return None


async def auto_rate_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback — runs every 3 hours."""
    is_auto = await db.get_setting("is_auto_currency") == "1"
    if not is_auto:
        return
    await _fetch_and_save_rate()

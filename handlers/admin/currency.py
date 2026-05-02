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
from handlers.utils import admin_filter, get_admin_ids
from handlers.admin._helpers import cancel_conversation, require_admin_callback

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
    mode_text = "🤖 خودکار (API)" if is_auto else "✏️ دستی"
    await update.message.reply_text(
        f"💰 *تنظیمات نرخ ارز*\n\n"
        f"نرخ فعلی: *{current:,.0f} تومان*\n"
        f"وضعیت: {mode_text}\n\n"
        f"یک گزینه را انتخاب کنید:",
        parse_mode="Markdown",
        reply_markup=currency_rate_mode_keyboard(),
    )


# ── Manual branch ────────────────────────────────────────────────────────────

async def rate_manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin chose Manual Update — start the manual-entry conversation."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    await db.set_setting("is_auto_currency", "0")
    current = await db.get_currency_rate()
    await query.message.reply_text(
        f"✏️ *به‌روزرسانی دستی*\n\nنرخ فعلی: *{current:,.0f} تومان*\n\nنرخ جدید را وارد کنید (تومان به ازای هر واحد ارز خارجی):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return SR_VALUE


async def sr_get_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)
    try:
        rate = float(update.message.text.strip().replace(",", ""))
        if rate < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ مقدار نامعتبر است. یک عدد مثبت وارد کنید:")
        return SR_VALUE
    await db.set_setting("currency_rate", str(rate))
    await update.message.reply_text(
        f"✅ نرخ ارز با موفقیت به *{rate:,.2f} تومان* تغییر یافت.",
        parse_mode="Markdown",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ── Auto branch ──────────────────────────────────────────────────────────────

async def rate_auto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin chose Auto Update — enable the flag and immediately fetch once."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    await db.set_setting("is_auto_currency", "1")
    rate = await _fetch_and_save_rate()
    if rate:
        await query.edit_message_text(
            f"✅ به‌روزرسانی خودکار *فعال شد*.\nنرخ دریافت شده از API: *{rate:,} تومان*\n"
            f"_(هر ۳ ساعت یک‌بار به‌روز می‌شود)_",
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            "❌ به‌روزرسانی خودکار فعال شد، اما دریافت اولیه از API با *خطا* مواجه شد. "
            "تلاش مجدد در نوبت بعدی (۳ ساعت دیگر) انجام خواهد شد.",
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
    rate = await _fetch_and_save_rate()
    if rate is None:
        for admin_id in get_admin_ids():
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "⚠️ <b>خطا در به‌روزرسانی خودکار نرخ ارز</b>\n\n"
                        "دریافت نرخ از API Nobitex با خطا مواجه شد.\n"
                        "نرخ ارز بدون تغییر باقی مانده است."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                logger.warning("Could not notify admin %s about rate-fetch failure.", admin_id)

"""
handlers/admin/discounts.py — Discount management and conversation handler.

State machine:
    ADD_DISCOUNT: AD_CODE → AD_PERCENT → (save)
"""

from typing import Optional

import aiosqlite
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from database import DB_PATH
from keyboards import (
    admin_main_menu_keyboard,
    discounts_list_keyboard,
    discount_detail_keyboard,
    cancel_keyboard,
    back_inline_keyboard,
)
from handlers.utils import admin_filter
from handlers.admin._helpers import CTX_DISCOUNT, cancel_conversation

# ── Conversation states ──────────────────────────────────────────────────────

AD_CODE = 30
AD_PERCENT = 31


# ── Discount list & detail ───────────────────────────────────────────────────

async def manage_discounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not admin_filter(update):
        return
    discounts = await db.get_all_discounts()
    text = "🏷 *Discount Management*\n\nSelect a discount to manage, or add a new one."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=discounts_list_keyboard(discounts),
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=discounts_list_keyboard(discounts),
        )


async def discount_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # callback_data = "admin_discount_<code>"
    code = "_".join(query.data.split("_")[2:])
    discount = await db.get_discount(code) or await _get_discount_any(code)
    if not discount:
        await query.edit_message_text("Discount not found.")
        return
    status = "✅ Active" if discount["is_active"] else "❌ Inactive"
    pct = discount.get("percentage_discount", discount.get("amount", 0))
    await query.edit_message_text(
        f"🏷 Code: <code>{discount['code']}</code>\nDiscount: {pct}%\nStatus: {status}",
        parse_mode="HTML",
        reply_markup=discount_detail_keyboard(code),
    )


async def _get_discount_any(code: str) -> Optional[dict]:
    """Fetch discount regardless of active status (for admin view)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM Discounts WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def discount_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # callback_data = "admin_discount_delete_<code>"
    code = "_".join(query.data.split("_")[3:])
    await db.delete_discount(code)
    await query.edit_message_text(
        "🗑 Discount deleted.",
        reply_markup=back_inline_keyboard("admin_discount_list"),
    )


# ── Add discount conversation ────────────────────────────────────────────────

async def add_discount_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data[CTX_DISCOUNT] = {}
    await query.message.reply_text(
        "➕ *Add Discount Code*\n\nStep 1/2: Enter the discount *code* (text string):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AD_CODE


async def ad_get_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    code = update.message.text.strip()
    if not code:
        await update.message.reply_text("❌ Code cannot be empty. Try again:")
        return AD_CODE
    context.user_data[CTX_DISCOUNT]["code"] = code
    await update.message.reply_text(
        "Step 2/2: Enter the *discount percentage* (1–100):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AD_PERCENT


async def ad_get_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    try:
        pct = int(update.message.text.strip())
        if not (1 <= pct <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Enter an integer between 1 and 100:")
        return AD_PERCENT
    code = context.user_data[CTX_DISCOUNT]["code"]
    await db.add_discount(code, pct)
    context.user_data.pop(CTX_DISCOUNT, None)
    await update.message.reply_text(
        f"✅ Discount code <code>{code}</code> ({pct}%) added.",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END

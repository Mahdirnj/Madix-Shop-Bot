"""
handlers/admin/cards.py — Card management and conversation handler.

State machine:
    ADD_CARD: AC_NUMBER → AC_HOLDER → (save)
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    admin_main_menu_keyboard,
    cards_list_keyboard,
    card_detail_keyboard,
    cancel_keyboard,
    back_inline_keyboard,
)
from handlers.utils import admin_filter
from handlers.admin._helpers import CTX_CARD, cancel_conversation

# ── Conversation states ──────────────────────────────────────────────────────

AC_NUMBER = 10
AC_HOLDER = 11


# ── Card list & detail ───────────────────────────────────────────────────────

async def manage_cards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not admin_filter(update):
        return
    cards = await db.get_all_cards()
    text = "💳 *Card Management*\n\nSelect a card to manage, or add a new one."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=cards_list_keyboard(cards),
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=cards_list_keyboard(cards),
        )


async def card_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    card_id = int(query.data.split("_")[-1])
    cards = await db.get_all_cards()
    card = next((c for c in cards if c["card_id"] == card_id), None)
    if not card:
        await query.edit_message_text("Card not found.")
        return
    status = "✅ Active" if card["is_active"] else "❌ Inactive"
    holder = card.get("cardholder_name") or "N/A"
    await query.edit_message_text(
        f"💳 Card: <code>{card['card_number']}</code>\n"
        f"Cardholder: {holder}\n"
        f"Status: {status}",
        parse_mode="HTML",
        reply_markup=card_detail_keyboard(card_id, bool(card["is_active"])),
    )


async def card_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    card_id = int(query.data.split("_")[-1])
    new_status = await db.toggle_card_status(card_id)
    status_text = "activated ✅" if new_status else "deactivated ❌"
    await query.edit_message_text(
        f"Card has been {status_text}.",
        reply_markup=back_inline_keyboard("admin_card_list"),
    )


async def card_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    card_id = int(query.data.split("_")[-1])
    await db.delete_card(card_id)
    await query.edit_message_text(
        "🗑 Card deleted.",
        reply_markup=back_inline_keyboard("admin_card_list"),
    )


# ── Add card conversation ────────────────────────────────────────────────────

async def add_card_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data[CTX_CARD] = {}
    await query.message.reply_text(
        "➕ *Add New Card*\n\nStep 1/2: Enter the *card number*:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AC_NUMBER


async def ac_get_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    card_number = update.message.text.strip()
    if not card_number:
        await update.message.reply_text("❌ Card number cannot be empty. Try again:")
        return AC_NUMBER
    context.user_data[CTX_CARD]["card_number"] = card_number
    await update.message.reply_text(
        "Step 2/2: Enter the *cardholder name*:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AC_HOLDER


async def ac_get_holder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    holder = update.message.text.strip()
    card_number = context.user_data[CTX_CARD]["card_number"]
    card_id = await db.add_card(card_number, holder)
    context.user_data.pop(CTX_CARD, None)
    await update.message.reply_text(
        f"✅ Card added (ID: {card_id}):\n"
        f"<code>{card_number}</code>\n"
        f"Cardholder: {holder}",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END

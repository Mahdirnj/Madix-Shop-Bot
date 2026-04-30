"""
handlers/admin/broadcast.py — Broadcast conversation handler.

State machine:
    BROADCAST: BC_MESSAGE → (send to all)
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import admin_main_menu_keyboard, cancel_keyboard
from handlers.utils import admin_filter
from handlers.admin._helpers import cancel_conversation

logger = logging.getLogger(__name__)

# ── Conversation state ───────────────────────────────────────────────────────

BC_MESSAGE = 40


# ── Handlers ─────────────────────────────────────────────────────────────────

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not admin_filter(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📣 *Broadcast*\n\nSend the message you want to broadcast to all users.\n_(HTML supported)_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return BC_MESSAGE


async def bc_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    message_text = update.message.text
    users = await db.get_all_users()
    sent, failed = 0, 0
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["user_id"], text=message_text, parse_mode="HTML"
            )
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"📣 Broadcast complete.\n✅ Sent: {sent}\n❌ Failed: {failed}",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END

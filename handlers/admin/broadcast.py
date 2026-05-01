"""
handlers/admin/broadcast.py — Broadcast conversation handler.

State machine:
    BROADCAST: BC_MESSAGE → preview → BC_CONFIRM → (send to all | cancel)
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import admin_main_menu_keyboard, cancel_keyboard, broadcast_confirm_keyboard
from handlers.utils import admin_filter
from handlers.admin._helpers import cancel_conversation

logger = logging.getLogger(__name__)

# ── Conversation states ──────────────────────────────────────────────────────

BC_MESSAGE = 40
BC_CONFIRM = 41

# Context key for storing the draft message
_CTX_BC_TEXT = "bc_draft_text"


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


async def bc_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the draft message and ask for confirmation."""
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)

    context.user_data[_CTX_BC_TEXT] = update.message.text
    users = await db.get_all_users()
    user_count = len(users)

    await update.message.reply_text(
        f"📣 *Broadcast Preview*\n\n"
        f"──────────────────\n"
        f"{update.message.text}\n"
        f"──────────────────\n\n"
        f"This message will be sent to *{user_count}* users.\n"
        f"Are you sure you want to send it?",
        parse_mode="Markdown",
        reply_markup=broadcast_confirm_keyboard(),
    )
    return BC_CONFIRM


async def bc_confirm_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the Yes/No confirmation for broadcast."""
    if update.message.text != "✅ Yes, Send":
        # Any other text (including "❌ Cancel") cancels the broadcast
        context.user_data.pop(_CTX_BC_TEXT, None)
        await update.message.reply_text(
            "❌ Broadcast cancelled.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return ConversationHandler.END

    message_text = context.user_data.pop(_CTX_BC_TEXT, None)
    if not message_text:
        await update.message.reply_text(
            "⚠️ No message found. Please start over.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return ConversationHandler.END

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

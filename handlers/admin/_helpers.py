"""
handlers/admin/_helpers.py — Shared context keys and helpers for admin handlers.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from keyboards import admin_main_menu_keyboard
from handlers.utils import admin_filter

# Context keys used to carry partial data through admin conversations
CTX_PRODUCT = "new_product"
CTX_EDIT_PRODUCT = "edit_product"
CTX_DISCOUNT = "new_discount"
CTX_CARD = "new_card"


async def require_admin_callback(update: Update) -> bool:
    """Return True when an inline admin callback was sent by an admin."""
    if admin_filter(update):
        return True

    query = update.callback_query
    if query:
        await query.answer("Access denied.", show_alert=True)
    return False


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shared cancel fallback for all admin ConversationHandlers."""
    context.user_data.pop(CTX_PRODUCT, None)
    context.user_data.pop(CTX_EDIT_PRODUCT, None)
    context.user_data.pop(CTX_DISCOUNT, None)
    context.user_data.pop(CTX_CARD, None)
    await update.message.reply_text(
        "❌ عملیات لغو شد.",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END

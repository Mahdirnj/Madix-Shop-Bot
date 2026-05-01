"""
handlers/admin/panel.py — Admin entry point and generic navigation callbacks.
"""

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from keyboards import admin_main_menu_keyboard
from handlers.utils import admin_filter


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point: /admin command — only visible to admins."""
    if not admin_filter(update):
        await update.message.reply_text("⛔ دسترسی غیرمجاز.")
        return
    await db.ensure_user(update.effective_user.id)
    await update.message.reply_text(
        "👑 به پنل مدیریت خوش آمدید.",
        reply_markup=admin_main_menu_keyboard(),
    )


async def admin_back_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generic back-to-main callback."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "👑 پنل مدیریت — یک گزینه را انتخاب کنید:",
        reply_markup=None,
    )

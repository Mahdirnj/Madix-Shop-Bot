"""
handlers/admin/statistics.py — Admin statistics handler.
"""

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from keyboards import admin_main_menu_keyboard
from handlers.utils import admin_filter


async def admin_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show aggregate statistics to the admin."""
    if not admin_filter(update):
        return
    stats = await db.get_statistics()
    text = (
        f"📊 <b>Statistics</b>\n\n"
        f"👥 Total Users: <b>{stats['total_users']}</b>\n"
        f"💰 Total Sales Volume: <b>{stats['total_sales']:,} T</b>\n"
        f"⏳ Pending Payment Orders: <b>{stats['pending_orders']}</b>\n"
        f"🔄 Processing Orders: <b>{stats['processing_orders']}</b>\n"
        f"💳 Pending Transactions: <b>{stats['pending_transactions']}</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=admin_main_menu_keyboard())

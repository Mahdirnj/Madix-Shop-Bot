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
        f"📊 <b>آمار و گزارشات</b>\n\n"
        f"👥 کل کاربران: <b>{stats['total_users']}</b>\n"
        f"💰 کل حجم فروش: <b>{stats['total_sales']:,} تومان</b>\n"
        f"⏳ سفارشات در انتظار پرداخت: <b>{stats['pending_orders']}</b>\n"
        f"🔄 سفارشات در حال پردازش: <b>{stats['processing_orders']}</b>\n"
        f"💳 تراکنش‌های مالی در انتظار: <b>{stats['pending_transactions']}</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=admin_main_menu_keyboard())

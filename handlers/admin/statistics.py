"""
handlers/admin/statistics.py — Admin statistics handler.
"""

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from keyboards import admin_main_menu_keyboard
from handlers.utils import admin_filter
from datetime import datetime, timedelta


async def admin_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show aggregate statistics to the admin in a clean, compact format."""
    if not admin_filter(update):
        return
    stats = await db.get_statistics()
    
    # Format top products list
    top_products_text = ""
    if stats['top_products']:
        for idx, (name, count) in enumerate(stats['top_products'], 1):
            top_products_text += f"  {idx}. {name} ({count})\n"
    else:
        top_products_text = "  درخواستی وجود ندارد"
    
    # Calculate total pending actions
    total_pending = stats['pending_payment'] + stats['processing_orders'] + stats['pending_transactions']
    pending_status_emoji = "🔴" if total_pending > 0 else "🟢"
    
    # Build compact stats message with sections
    text = (
        f"📊 <b>آمار و گزارشات</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Pending Status Header (Prominent)
        f"{pending_status_emoji} <b>وضعیت فوری</b>\n"
        f"📍 کل موارد منتظر تایید: <b>{total_pending}</b>\n"
        f"├─ ⏳ در انتظار پرداخت: <b>{stats['pending_payment']}</b>\n"
        f"├─ 🔄 درحال پردازش: <b>{stats['processing_orders']}</b>\n"
        f"└─ 💸 تایید کیف‌پول: <b>{stats['pending_transactions']}</b>\n\n"
        
        # Revenue & Conversion Section
        f"💼 <b>عملکرد فروش</b>\n"
        f"💰 کل درآمد: <b>{stats['total_sales']:,} تومان</b>\n"
        f"✅ سفارشات تکمیل‌شده: <b>{stats['completed_orders']}</b>\n"
        f"📊 نسبت تبدیل: <b>{stats['conversion_rate']}%</b>\n\n"
        
        # Payment Methods Section
        f"💳 <b>روش‌های پرداخت</b>\n"
        f"💰 کیف‌پول: <b>{stats['wallet_pct']}%</b> ({stats['wallet_orders']})\n"
        f"🏦 کارت بانکی: <b>{stats['card_pct']}%</b> ({stats['card_orders']})\n\n"
        
        # Users & Growth Section
        f"👥 <b>رشد کاربران</b>\n"
        f"👤 کل کاربران: <b>{stats['total_users']}</b>\n"
        f"📍 امروز: <b>{stats['new_users_today']}</b>\n"
        f"📍 این هفته: <b>{stats['new_users_week']}</b>\n\n"
        
        # Top Products Section
        f"🏆 <b>محصولات پرفروش</b>\n"
        + top_products_text
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=admin_main_menu_keyboard())

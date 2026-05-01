"""
handlers/shop/profile.py — User profile and support handlers.
"""

import html

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import get_support_handle


async def user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await db.ensure_user(user_id)
    user = await db.get_user(user_id)
    wallet = user["wallet_balance"] if user else 0
    orders = await db.get_user_orders(user_id)

    status_map = {
        "PENDING_PAYMENT": "⏳ در انتظار پرداخت",
        "PROCESSING":      "🔄 در حال پردازش",
        "COMPLETED":       "✅ تکمیل شده",
        "REJECTED":        "❌ لغو شده",
    }

    text = f"👤 <b>پروفایل کاربری</b>\n\n💰 موجودی کیف پول: <b>{wallet:,} تومان</b>\n"

    if not orders:
        text += "\n📋 شما هنوز هیچ سفارشی ثبت نکرده‌اید."
    else:
        recent = orders[:10]
        text += f"\n📋 <b>سفارشات اخیر</b> ({len(recent)} مورد آخر):\n"
        for o in recent:
            status = status_map.get(o["status"], o["status"])
            text += f"\n• <b>{html.escape(o['product_name'])}</b> — {o['final_price_paid']:,} تومان — {status}"

    await update.message.reply_text(text, parse_mode="HTML")


async def user_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    support_handle = await get_support_handle()
    await update.message.reply_text(
        "🎧 <b>پشتیبانی</b>\n\n"
        "اگر سوال یا مشکلی دارید، لطفاً با تیم پشتیبانی ما در تماس باشید:\n\n"
        f"📩 {support_handle}",
        parse_mode="HTML",
    )

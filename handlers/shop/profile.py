"""
handlers/shop/profile.py — User profile and support handlers.
"""

import html

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import get_support_handle, fmt_datetime
from handlers.emoji import get_all_ces


async def user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    await db.ensure_user(
        tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        language_code=tg_user.language_code,
    )
    user_id = tg_user.id
    user = await db.get_user(user_id)
    wallet = user["wallet_balance"] if user else 0
    orders = await db.get_user_orders(user_id)
    ces = await get_all_ces()

    status_map = {
        "PENDING_PAYMENT": ("⏳", "در انتظار پرداخت"),
        "PROCESSING":      ("🔄", "در حال پردازش"),
        "COMPLETED":       ("✅", "تکمیل شده"),
        "REJECTED":        ("❌", "لغو شده"),
    }

    lines = [
        f"{ces['emoji_profile']} <b>پروفایل کاربری</b>",
        "",
        f"{ces['emoji_wallet']} <b>موجودی کیف پول</b>: {wallet:,} تومان",
    ]

    if not orders:
        lines.append("")
        lines.append("📋 شما هنوز هیچ سفارشی ثبت نکرده‌اید.")
    else:
        # Count orders by status
        status_counts = {}
        for o in orders:
            st = o["status"]
            status_counts[st] = status_counts.get(st, 0) + 1

        lines.append("")
        lines.append("<b>📊 خلاصه سفارشات</b>")
        for st in ["COMPLETED", "PROCESSING", "PENDING_PAYMENT", "REJECTED"]:
            if st in status_counts:
                icon, label = status_map.get(st, ("❓", st))
                lines.append(f"  {icon} {label}: <b>{status_counts[st]}</b>")

        # Display last 5 orders (newest at bottom, oldest at top)
        lines.append("")
        lines.append("<b>📋 آخرین سفارشات</b>")
        lines.append("")

        for o in reversed(list(orders[:5])):
            icon = status_map.get(o["status"], ("❓", o["status"]))[0]
            product_name = html.escape(o.get("product_name", "محصول نامشخص"))
            price = o.get("final_price_paid", 0)
            order_date = fmt_datetime(o.get("created_at", ""))

            lines.append(f"  {icon} <b>#{o['order_id']}</b> {product_name}")
            lines.append(f"     {price:,} تومان  •  {order_date}")
            if o.get("status") == "REJECTED" and o.get("rejection_reason"):
                lines.append(f"     📋 <i>دلیل لغو: {html.escape(o['rejection_reason'])}</i>")
            lines.append("")

    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="HTML")


async def user_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    support_handle = await get_support_handle()
    ces = await get_all_ces()
    await update.message.reply_text(
        f"{ces['emoji_support']} <b>پشتیبانی و کمک</b>\n\n"
        "<i>ما اینجا هستیم تا کمکتان کنیم!</i>\n\n"
        "<b>درباره چه چیزی می‌توانیم کمکتان کنیم؟</b>\n"
        f"  • ❌ مشکل در پرداخت یا سفارش\n"
        f"  • {ces['emoji_question']} سوالات درباره محصولات\n"
        f"  • {ces['emoji_wallet']} مشکلات کیف پول\n"
        f"  • ⚙️ تغییر و بروزرسانی اطلاعات\n"
        f"  • {ces['emoji_lock']} مشکلات امنیتی\n\n"
        "<b>📞 تماس با ما</b>\n"
        f"📱 تلگرام: <b>{html.escape(support_handle)}</b>\n\n"
        "<i>ساعات پاسخگویی: هر روز ۹ صبح تا ۹ شب (وقت تهران)</i>\n"
        "<i>معمولاً در کمتر از ۱۰ دقیقه پاسخ می‌دهیم.</i>",
        parse_mode="HTML",
    )

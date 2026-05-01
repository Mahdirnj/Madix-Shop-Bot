"""
handlers/shop/profile.py — User profile and support handlers.
"""

import html
from datetime import datetime, timezone, timedelta

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import get_support_handle
from handlers.emoji import get_all_ces

# Tehran is UTC+3:30
_TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def _fmt_dt(raw: str) -> str:
    """Convert ISO UTC datetime to beautiful Tehran-time format."""
    if not raw:
        return "—"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_teh = dt.astimezone(_TEHRAN_TZ)
        return dt_teh.strftime("%d/%m/%Y — %H:%M")
    except Exception:
        return raw


async def user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await db.ensure_user(user_id)
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

        # Display orders
        lines.append("")
        lines.append("<b>📋 سفارشات شما</b> (آخرین ۱۰ مورد)")
        lines.append("—" * 40)

        for i, o in enumerate(orders[:10], 1):
            icon, status_text = status_map.get(o["status"], ("❓", o["status"]))
            product_name = html.escape(o.get("product_name", "محصول نامشخص"))
            price = o.get("final_price_paid", 0)
            order_date = _fmt_dt(o.get("created_at"))
            count_line = ""
            if o.get("input_count"):
                count_line = f"\n  🔢 تعداد: <b>{o['input_count']:,}</b>"

            lines.append(
                f"\n<b>#{o['order_id']}</b> {icon} {status_text}"
                f"\n  📦 محصول: {product_name}"
                f"\n  {ces['emoji_wallet']} مبلغ: <b>{price:,} تومان</b>{count_line}"
                f"\n  📅 تاریخ: {order_date}"
                f"\n"
            )

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

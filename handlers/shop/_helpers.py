"""
handlers/shop/_helpers.py — Shared helpers, context keys, and state constants for the shop package.
"""

import html
import random

from telegram.ext import ContextTypes

import database as db
from keyboards import checkout_keyboard

# ── Context keys ─────────────────────────────────────────────────────────────

CTX_ORDER = "shop_order"
CTX_TOPUP = "shop_topup"

# ── Conversation states ─────────────────────────────────────────────────────

(
    COLLECT_TG_ID,
    COLLECT_EMAIL,
    COLLECT_PASSWORD,
    COLLECT_COUNT,
    COLLECT_DISCOUNT,
    COLLECT_RECEIPT,
    CHECKOUT,
) = range(100, 107)

(
    TOPUP_AMOUNT,
    TOPUP_RECEIPT,
) = range(110, 112)


# ── Invoice helpers ──────────────────────────────────────────────────────────

def build_invoice_text(order: dict) -> str:
    """Format the order summary text."""
    lines = ["🧾 <b>خلاصه سفارش</b>\n"]
    lines.append(f"📦 محصول: <b>{html.escape(order['product_name'])}</b>")
    if order.get("input_count"):
        lines.append(f"🔢 تعداد: <b>{order['input_count']:,}</b>")
    lines.append(f"💰 قیمت: <b>{order['final_price']:,} تومان</b>")
    if order.get("discount_pct"):
        lines.append(f"🏷 تخفیف: <b>{order['discount_pct']}%</b> اعمال شد")
    if order.get("input_telegram_id"):
        lines.append(f"📱 آیدی تلگرام: <code>{html.escape(order['input_telegram_id'])}</code>")
    if order.get("input_email"):
        lines.append(f"📧 ایمیل: <code>{html.escape(order['input_email'])}</code>")
    if order.get("input_password"):
        lines.append("🔑 رمز عبور: ✅ ارسال شده")
    return "\n".join(lines)


async def show_invoice(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render the invoice and end the input-collection sub-flow."""
    order = context.user_data[CTX_ORDER]
    user = await db.get_user(message.chat.id)
    wallet = user["wallet_balance"] if user else 0
    await message.reply_text(
        build_invoice_text(order),
        parse_mode="HTML",
        reply_markup=checkout_keyboard(wallet),
    )
    return CHECKOUT


async def advance(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Move to the next required input step, or show the invoice when all
    required inputs have been collected.
    """
    order = context.user_data[CTX_ORDER]

    if order.get("requires_count") and order.get("input_count") is None:
        await message.reply_text(
            f"🔢 لطفاً <b>تعداد</b> مورد نظر را وارد کنید:\n"
            f"(قیمت واحد: <b>{order['unit_price']:,} تومان</b>)\n\n"
            "<i>برای انصراف هر زمان که بخواهید /cancel را بفرستید.</i>",
            parse_mode="HTML",
        )
        return COLLECT_COUNT

    if order["requires_telegram_id"] and order["input_telegram_id"] is None:
        await message.reply_text(
            "📱 لطفاً <b>آیدی تلگرام</b> خود را ارسال کنید\n"
            "(مثلاً <code>@mahdirnj</code> یا فقط <code>mahdirnj</code>).\n\n"
            "<i>برای انصراف هر زمان که بخواهید /cancel را بفرستید.</i>",
            parse_mode="HTML",
        )
        return COLLECT_TG_ID

    if order["requires_email"] and order["input_email"] is None:
        await message.reply_text(
            "📧 لطفاً <b>آدرس ایمیل</b> خود را ارسال کنید.\n\n"
            "<i>برای انصراف هر زمان که بخواهید /cancel را بفرستید.</i>",
            parse_mode="HTML",
        )
        return COLLECT_EMAIL

    if order["requires_password"] and order["input_password"] is None:
        await message.reply_text(
            "🔑 لطفاً <b>رمز عبور</b> اکانت خود را ارسال کنید.\n\n"
            "<i>برای انصراف هر زمان که بخواهید /cancel را بفرستید.</i>",
            parse_mode="HTML",
        )
        return COLLECT_PASSWORD

    return await show_invoice(message, context)


async def send_card_and_ask_receipt(message, context, amount: int):
    """Pick a random active card and ask user to send a receipt photo."""
    cards = await db.get_all_cards(active_only=True)
    if not cards:
        await message.reply_text(
            "❌ در حال حاضر هیچ کارت بانکی فعالی در سیستم ثبت نشده است. "
            "لطفاً بعداً تلاش کنید یا با پشتیبانی تماس بگیرید."
        )
        return False
    card = random.choice(cards)
    holder = html.escape(card.get("cardholder_name") or "")
    holder_line = f"\n👤 صاحب کارت: <b>{holder}</b>" if holder else ""
    await message.reply_text(
        f"💳 لطفاً مبلغ <b>{amount:,} تومان</b> را به شماره کارت زیر واریز کنید:\n\n"
        f"<code>{html.escape(card['card_number'])}</code>{holder_line}\n\n"
        "پس از واریز، <b>تصویر رسید</b> خود را در اینجا ارسال کنید.",
        parse_mode="HTML",
    )
    return True

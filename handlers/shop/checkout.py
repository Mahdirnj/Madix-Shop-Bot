"""
handlers/shop/checkout.py — Checkout conversation: input collection, payment, receipts.

Conversation flow:
    buy_now_callback
      → COLLECT_TG_ID → COLLECT_EMAIL → COLLECT_PASSWORD
      → invoice shown
      → shop_discount  → COLLECT_DISCOUNT  → invoice re-shown
      → shop_pay_card  → COLLECT_RECEIPT   → admin notified
      → shop_pay_wallet                    → wallet deducted / admin notified
"""

import html
import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ConversationHandler, ContextTypes

import database as db
from keyboards import main_menu_keyboard, receipt_sent_keyboard
from handlers.utils import get_admin_ids
from handlers.shop._helpers import (
    CTX_ORDER,
    COLLECT_TG_ID, COLLECT_EMAIL, COLLECT_PASSWORD,
    COLLECT_DISCOUNT, COLLECT_RECEIPT, CHECKOUT,
    advance, show_invoice, send_card_and_ask_receipt,
)

logger = logging.getLogger(__name__)


# ── Buy entry point ─────────────────────────────────────────────────────────

async def buy_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await db.get_product(product_id)
    if not product or not product["is_active"]:
        try:
            await query.edit_message_text("❌ این محصول دیگر موجود نیست.")
        except BadRequest:
            pass
        return ConversationHandler.END
    rate = await db.get_currency_rate()
    final_price = int(product["base_currency_price"] * rate) + product["admin_profit"]
    context.user_data[CTX_ORDER] = {
        "product_id":           product_id,
        "product_name":         product["name"],
        "unit_price":           final_price,
        "base_price":           final_price,
        "final_price":          final_price,
        "discount_pct":         0,
        "discount_code":        None,
        "input_telegram_id":    None,
        "input_email":          None,
        "input_password":       None,
        "input_count":          None,
        "requires_telegram_id": bool(product["requires_telegram_id"]),
        "requires_email":       bool(product["requires_email"]),
        "requires_password":    bool(product["requires_password"]),
        "requires_count":       bool(product["requires_count"]),
    }
    return await advance(query.message, context)


# ── Input collectors ─────────────────────────────────────────────────────────

async def shop_get_tg_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[CTX_ORDER]["input_telegram_id"] = update.message.text.strip()
    return await advance(update.message, context)


async def shop_get_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text(
            "❌ لطفاً یک عدد صحیح مثبت وارد کنید:",
        )
        return COLLECT_COUNT
    order = context.user_data[CTX_ORDER]
    count = int(text)
    order["input_count"] = count
    # Recalculate price: unit_price * count + profit already baked into unit_price
    # unit_price = base_currency_price * rate + admin_profit (per-unit)
    # final = unit_price * count
    order["final_price"] = order["unit_price"] * count
    order["base_price"] = order["final_price"]
    return await advance(update.message, context)


async def shop_get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[CTX_ORDER]["input_email"] = update.message.text.strip()
    return await advance(update.message, context)


async def shop_get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[CTX_ORDER]["input_password"] = update.message.text.strip()
    return await advance(update.message, context)


# ── Discount ─────────────────────────────────────────────────────────────────

async def shop_discount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped '🏷 Enter Discount Code' on the invoice."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🏷 لطفاً <b>کد تخفیف</b> خود را ارسال کنید:",
        parse_mode="HTML",
    )
    return COLLECT_DISCOUNT


async def shop_collect_discount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate and apply the discount code, then re-show the invoice."""
    code = update.message.text.strip()
    discount = await db.get_discount(code)
    if not discount:
        await update.message.reply_text(
            "❌ کد تخفیف نامعتبر یا منقضی شده است. در حال بازگشت به فاکتور..."
        )
        return await show_invoice(update.message, context)

    user_id = update.effective_user.id
    already_used = await db.check_discount_used(user_id, code)
    if already_used:
        await update.message.reply_text(
            "❌ شما قبلاً از این کد تخفیف استفاده کرده‌اید. در حال بازگشت به فاکتور..."
        )
        return await show_invoice(update.message, context)

    order = context.user_data[CTX_ORDER]
    pct = discount["percentage_discount"]
    new_price = int(order["base_price"] * (1 - pct / 100))
    order["final_price"] = new_price
    order["discount_pct"] = pct
    order["discount_code"] = code

    await update.message.reply_text(
        f"✅ کد تخفیف <code>{html.escape(code)}</code> اعمال شد! "
        f"<b>{pct}%</b> تخفیف ← قیمت جدید: <b>{new_price:,} تومان</b>",
        parse_mode="HTML",
    )
    return await show_invoice(update.message, context)


# ── Pay with card ────────────────────────────────────────────────────────────

async def shop_pay_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped '💳 Pay with Card' on the invoice."""
    query = update.callback_query
    await query.answer()
    order = context.user_data.get(CTX_ORDER)
    if not order:
        await query.answer("نشست شما به پایان رسیده است. لطفاً دوباره تلاش کنید.", show_alert=True)
        return ConversationHandler.END
    ok = await send_card_and_ask_receipt(query.message, context, order["final_price"])
    if not ok:
        return ConversationHandler.END
    return COLLECT_RECEIPT


async def shop_collect_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User sent a receipt photo for a card order payment."""
    if not update.message.photo:
        await update.message.reply_text("❌ لطفاً <b>عکس</b> رسید پرداخت خود را ارسال کنید.", parse_mode="HTML")
        return COLLECT_RECEIPT

    order = context.user_data.get(CTX_ORDER)
    if not order:
        await update.message.reply_text("❌ نشست شما به پایان رسیده است. لطفاً دوباره تلاش کنید.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    user_id = update.effective_user.id
    photo_id = update.message.photo[-1].file_id

    # Create the order record with PENDING_PAYMENT status
    order_id = await db.create_order(
        user_id=user_id,
        product_id=order["product_id"],
        final_price_paid=order["final_price"],
        payment_method="CARD_TRANSFER",
        input_telegram_id=order.get("input_telegram_id"),
        input_email=order.get("input_email"),
        input_password=order.get("input_password"),
        input_count=order.get("input_count"),
        discount_code=order.get("discount_code"),
        status="PENDING_PAYMENT",
    )

    # Save receipt as a transaction linked to the order so admin can review
    tx_id = await db.create_transaction(
        user_id=user_id,
        amount=order["final_price"],
        receipt_photo_id=photo_id,
        order_id=order_id,
    )

    context.user_data.pop(CTX_ORDER, None)

    await update.message.reply_text(
        f"✅ رسید شما دریافت شد! سفارش شماره <b>#{order_id}</b> در انتظار تایید مدیریت است.\n"
        "به محض تایید پرداخت، به شما اطلاع داده خواهد شد.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    # Notify all admins
    count_line = f"\n🔢 تعداد: {order['input_count']:,}" if order.get("input_count") else ""
    admin_caption = (
        f"💳 <b>رسید سفارش جدید</b>\n\n"
        f"سفارش #{order_id}\n"
        f"کاربر: <code>{user_id}</code>\n"
        f"محصول: {html.escape(order['product_name'])}\n"
        f"مبلغ: {order['final_price']:,} تومان{count_line}"
    )
    for admin_id in get_admin_ids():
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=photo_id,
                caption=admin_caption,
                parse_mode="HTML",
                reply_markup=receipt_sent_keyboard(order_id),
            )
        except Exception:
            logger.warning("Could not notify admin %s about order %s.", admin_id, order_id)

    return ConversationHandler.END


# ── Pay with wallet ──────────────────────────────────────────────────────────

async def shop_pay_wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped '💰 Pay from Wallet' on the invoice."""
    query = update.callback_query
    order = context.user_data.get(CTX_ORDER)
    if not order:
        await query.answer()
        await query.message.reply_text("❌ نشست شما به پایان رسیده است. لطفاً دوباره تلاش کنید.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    user_id = update.effective_user.id
    final_price = order["final_price"]

    # Atomically deduct wallet only if sufficient — prevents race conditions
    success = await db.deduct_wallet_if_sufficient(user_id, final_price)
    if not success:
        # Re-fetch actual balance for the error message
        user = await db.get_user(user_id)
        wallet = user["wallet_balance"] if user else 0
        await query.answer(
            f"❌ موجودی کافی نیست. موجودی شما {wallet:,} تومان است اما به {final_price:,} تومان نیاز دارید.",
            show_alert=True,
        )
        return CHECKOUT

    # Deduction succeeded — create the order
    await query.answer()
    order_id = await db.create_order(
        user_id=user_id,
        product_id=order["product_id"],
        final_price_paid=final_price,
        payment_method="WALLET",
        input_telegram_id=order.get("input_telegram_id"),
        input_email=order.get("input_email"),
        input_password=order.get("input_password"),
        input_count=order.get("input_count"),
        discount_code=order.get("discount_code"),
        status="PROCESSING",
    )
    context.user_data.pop(CTX_ORDER, None)

    # Re-fetch for accurate post-deduction balance display
    user = await db.get_user(user_id)
    new_balance = user["wallet_balance"] if user else 0

    try:
        await query.edit_message_text(
            f"✅ پرداخت با موفقیت انجام شد!\n\n"
            f"سفارش شماره <b>#{order_id}</b> در حال پردازش است.\n"
            f"موجودی جدید کیف پول: <b>{new_balance:,} تومان</b>",
            parse_mode="HTML",
        )
    except BadRequest:
        pass

    await context.bot.send_message(
        chat_id=user_id,
        text="👇 منوی اصلی:",
        reply_markup=main_menu_keyboard(),
    )

    # Notify all admins
    admin_text = (
        f"💰 <b>سفارش جدید از کیف پول</b> (پرداخت خودکار)\n\n"
        f"سفارش #{order_id}\n"
        f"کاربر: <code>{user_id}</code>\n"
        f"محصول: {html.escape(order['product_name'])}\n"
        f"مبلغ: {final_price:,} تومان\n\n"
        f"وضعیت: <b>در حال پردازش</b> — لطفاً به صورت دستی تحویل دهید."
    )
    if order.get("input_telegram_id"):
        admin_text += f"\n📱 تلگرام: <code>{html.escape(order['input_telegram_id'])}</code>"
    if order.get("input_email"):
        admin_text += f"\n📧 ایمیل: <code>{html.escape(order['input_email'])}</code>"
    if order.get("input_password"):
        admin_text += f"\n🔑 رمز عبور: <code>{html.escape(order['input_password'])}</code>"

    from keyboards import order_review_keyboard
    for admin_id in get_admin_ids():
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                parse_mode="HTML",
                reply_markup=order_review_keyboard(order_id),
            )
        except Exception:
            logger.warning("Could not notify admin %s about wallet order %s.", admin_id, order_id)
    return ConversationHandler.END


# ── Cancel / exit ────────────────────────────────────────────────────────────

async def shop_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inline '❌ Cancel' button on the invoice."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop(CTX_ORDER, None)
    try:
        await query.edit_message_text("❌ سفارش لغو شد.")
    except BadRequest:
        pass
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="از منوی زیر ادامه دهید.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def shop_force_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/cancel command fallback during input collection."""
    context.user_data.pop(CTX_ORDER, None)
    await update.message.reply_text("❌ سفارش لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def shop_conv_menu_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User pressed a main-menu button while inside the conversation — exit gracefully."""
    from handlers.shop.browsing import shop_menu
    from handlers.shop.wallet import wallet_menu
    from handlers.shop.profile import user_profile, user_support

    context.user_data.pop(CTX_ORDER, None)
    text = update.message.text
    if text == "🛍 فروشگاه":
        await shop_menu(update, context)
    elif text == "👤 پروفایل من":
        await user_profile(update, context)
    elif text == "💰 کیف پول من":
        await wallet_menu(update, context)
    elif text == "🎧 پشتیبانی":
        await user_support(update, context)
    else:
        await update.message.reply_text("❌ سفارش لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

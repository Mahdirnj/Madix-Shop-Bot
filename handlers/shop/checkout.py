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
            await query.edit_message_text("❌ This product is no longer available.")
        except BadRequest:
            pass
        return ConversationHandler.END
    rate = await db.get_currency_rate()
    final_price = int(product["base_currency_price"] * rate) + product["admin_profit"]
    context.user_data[CTX_ORDER] = {
        "product_id":           product_id,
        "product_name":         product["name"],
        "base_price":           final_price,
        "final_price":          final_price,
        "discount_pct":         0,
        "input_telegram_id":    None,
        "input_email":          None,
        "input_password":       None,
        "requires_telegram_id": bool(product["requires_telegram_id"]),
        "requires_email":       bool(product["requires_email"]),
        "requires_password":    bool(product["requires_password"]),
    }
    return await advance(query.message, context)


# ── Input collectors ─────────────────────────────────────────────────────────

async def shop_get_tg_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[CTX_ORDER]["input_telegram_id"] = update.message.text.strip()
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
        "🏷 Please send your <b>discount code</b>:",
        parse_mode="HTML",
    )
    return COLLECT_DISCOUNT


async def shop_collect_discount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate and apply the discount code, then re-show the invoice."""
    code = update.message.text.strip()
    discount = await db.get_discount(code)
    if not discount:
        await update.message.reply_text(
            "❌ Invalid or expired discount code. Try a different code or press Cancel on the invoice."
        )
        return COLLECT_DISCOUNT

    order = context.user_data[CTX_ORDER]
    pct = discount["percentage_discount"]
    new_price = int(order["base_price"] * (1 - pct / 100))
    order["final_price"] = new_price
    order["discount_pct"] = pct

    await update.message.reply_text(
        f"✅ Discount code <code>{html.escape(code)}</code> applied! "
        f"<b>{pct}%</b> off → new price: <b>{new_price:,} Tomans</b>",
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
        await query.answer("Session expired. Please start over.", show_alert=True)
        return ConversationHandler.END
    ok = await send_card_and_ask_receipt(query.message, context, order["final_price"])
    if not ok:
        return ConversationHandler.END
    return COLLECT_RECEIPT


async def shop_collect_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User sent a receipt photo for a card order payment."""
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a <b>photo</b> of your receipt.", parse_mode="HTML")
        return COLLECT_RECEIPT

    order = context.user_data.get(CTX_ORDER)
    if not order:
        await update.message.reply_text("❌ Session expired. Please start over.", reply_markup=main_menu_keyboard())
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
        f"✅ Receipt received! Your order <b>#{order_id}</b> is pending admin approval.\n"
        "You will be notified once it is confirmed.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    # Notify all admins
    admin_caption = (
        f"💳 <b>New Order Receipt</b>\n\n"
        f"Order #{order_id}\n"
        f"User: <code>{user_id}</code>\n"
        f"Product: {html.escape(order['product_name'])}\n"
        f"Amount: {order['final_price']:,} T"
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
        await query.message.reply_text("❌ Session expired. Please start over.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    wallet = user["wallet_balance"] if user else 0
    final_price = order["final_price"]

    if wallet < final_price:
        await query.answer(
            f"❌ Insufficient balance. You have {wallet:,} T but need {final_price:,} T.",
            show_alert=True,
        )
        return CHECKOUT

    # Deduct wallet and create order
    await query.answer()
    await db.update_wallet(user_id, -final_price)
    order_id = await db.create_order(
        user_id=user_id,
        product_id=order["product_id"],
        final_price_paid=final_price,
        payment_method="WALLET",
        input_telegram_id=order.get("input_telegram_id"),
        input_email=order.get("input_email"),
        input_password=order.get("input_password"),
        status="PROCESSING",
    )
    context.user_data.pop(CTX_ORDER, None)

    try:
        await query.edit_message_text(
            f"✅ Payment successful!\n\n"
            f"Order <b>#{order_id}</b> is now being processed.\n"
            f"New wallet balance: <b>{wallet - final_price:,} T</b>",
            parse_mode="HTML",
        )
    except BadRequest:
        pass

    await context.bot.send_message(
        chat_id=user_id,
        text="👇 Main menu:",
        reply_markup=main_menu_keyboard(),
    )

    # Notify all admins
    admin_text = (
        f"💰 <b>New Wallet Order</b> (auto-paid)\n\n"
        f"Order #{order_id}\n"
        f"User: <code>{user_id}</code>\n"
        f"Product: {html.escape(order['product_name'])}\n"
        f"Amount: {final_price:,} T\n\n"
        f"Status: <b>PROCESSING</b> — please fulfill manually."
    )
    if order.get("input_telegram_id"):
        admin_text += f"\n📱 Telegram: <code>{html.escape(order['input_telegram_id'])}</code>"
    if order.get("input_email"):
        admin_text += f"\n📧 Email: <code>{html.escape(order['input_email'])}</code>"
    if order.get("input_password"):
        admin_text += f"\n🔑 Password: <code>{html.escape(order['input_password'])}</code>"

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
        await query.edit_message_text("❌ Order cancelled.")
    except BadRequest:
        pass
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="👇 Use the menu below to continue.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def shop_force_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/cancel command fallback during input collection."""
    context.user_data.pop(CTX_ORDER, None)
    await update.message.reply_text("❌ Order cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def shop_conv_menu_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User pressed a main-menu button while inside the conversation — exit gracefully."""
    from handlers.shop.browsing import shop_menu
    from handlers.shop.wallet import wallet_menu
    from handlers.shop.profile import user_profile, user_support

    context.user_data.pop(CTX_ORDER, None)
    text = update.message.text
    if text == "🛍 Shop":
        await shop_menu(update, context)
    elif text in ("👤 My Profile",):
        await user_profile(update, context)
    elif text == "💰 My Wallet":
        await wallet_menu(update, context)
    elif text in ("🎧 Support",):
        await user_support(update, context)
    else:
        await update.message.reply_text("❌ Order cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

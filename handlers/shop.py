"""
handlers/shop.py — User-facing shop, checkout, wallet, profile, and support handlers.

Conversation flows
──────────────────
build_shop_conv   (checkout):
    buy_now_callback
      → COLLECT_TG_ID → COLLECT_EMAIL → COLLECT_PASSWORD
      → invoice shown
      → shop_discount  → COLLECT_DISCOUNT  → invoice re-shown
      → shop_pay_card  → COLLECT_RECEIPT   → admin notified
      → shop_pay_wallet                    → wallet deducted / admin notified

build_topup_conv  (wallet top-up):
    topup_pay_card_callback
      → TOPUP_AMOUNT → TOPUP_RECEIPT       → admin notified
"""

import html
import logging
import os
import random

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import database as db
from keyboards import (
    main_menu_keyboard,
    shop_products_keyboard,
    product_buy_keyboard,
    checkout_keyboard,
    wallet_menu_keyboard,
    topup_payment_keyboard,
    receipt_sent_keyboard,
    topup_receipt_keyboard,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------

(
    COLLECT_TG_ID,
    COLLECT_EMAIL,
    COLLECT_PASSWORD,
    COLLECT_DISCOUNT,
    COLLECT_RECEIPT,
    CHECKOUT,
) = range(100, 106)

(
    TOPUP_AMOUNT,
    TOPUP_RECEIPT,
) = range(110, 112)

_CTX_ORDER  = "shop_order"
_CTX_TOPUP  = "shop_topup"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_admin_ids() -> list[int]:
    raw = os.getenv("ADMIN_IDS", "")
    return [int(p.strip()) for p in raw.split(",") if p.strip().isdigit()]


def _build_invoice_text(order: dict) -> str:
    lines = ["🧾 <b>Order Summary</b>\n"]
    lines.append(f"📦 Product: <b>{html.escape(order['product_name'])}</b>")
    lines.append(f"💰 Price: <b>{order['final_price']:,} Tomans</b>")
    if order.get("discount_pct"):
        lines.append(f"🏷 Discount: <b>{order['discount_pct']}%</b> applied")
    if order.get("input_telegram_id"):
        lines.append(f"📱 Telegram: <code>{html.escape(order['input_telegram_id'])}</code>")
    if order.get("input_email"):
        lines.append(f"📧 Email: <code>{html.escape(order['input_email'])}</code>")
    if order.get("input_password"):
        lines.append("🔑 Password: ✅ Provided")
    return "\n".join(lines)


async def _show_invoice(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render the invoice and end the input-collection sub-flow."""
    order  = context.user_data[_CTX_ORDER]
    user   = await db.get_user(message.chat.id)
    wallet = user["wallet_balance"] if user else 0
    await message.reply_text(
        _build_invoice_text(order),
        parse_mode="HTML",
        reply_markup=checkout_keyboard(wallet),
    )
    return CHECKOUT


async def _advance(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Move to the next required input step, or show the invoice when all
    required inputs have been collected.
    """
    order = context.user_data[_CTX_ORDER]

    if order["requires_telegram_id"] and order["input_telegram_id"] is None:
        await message.reply_text(
            "📱 Please send your <b>Telegram username</b>\n"
            "(e.g. <code>@mahdirnj</code> or just <code>mahdirnj</code>).\n\n"
            "<i>Send /cancel at any time to abort.</i>",
            parse_mode="HTML",
        )
        return COLLECT_TG_ID

    if order["requires_email"] and order["input_email"] is None:
        await message.reply_text(
            "📧 Please send your <b>Email address</b>.\n\n"
            "<i>Send /cancel at any time to abort.</i>",
            parse_mode="HTML",
        )
        return COLLECT_EMAIL

    if order["requires_password"] and order["input_password"] is None:
        await message.reply_text(
            "🔑 Please send the <b>Password</b> for your account.\n\n"
            "<i>Send /cancel at any time to abort.</i>",
            parse_mode="HTML",
        )
        return COLLECT_PASSWORD

    return await _show_invoice(message, context)


async def _send_card_and_ask_receipt(message, context, amount: int) -> None:
    """Pick a random active card and ask user to send a receipt photo."""
    cards = await db.get_all_cards(active_only=True)
    if not cards:
        await message.reply_text(
            "❌ No active payment cards are configured right now. "
            "Please try again later or contact support."
        )
        return False
    card = random.choice(cards)
    holder = html.escape(card.get("cardholder_name") or "")
    holder_line = f"\n👤 Cardholder: <b>{holder}</b>" if holder else ""
    await message.reply_text(
        f"💳 Please transfer <b>{amount:,} Tomans</b> to:\n\n"
        f"<code>{html.escape(card['card_number'])}</code>{holder_line}\n\n"
        "After transferring, send a <b>photo of the receipt</b> here.",
        parse_mode="HTML",
    )
    return True


# ---------------------------------------------------------------------------
# Shop browsing
# ---------------------------------------------------------------------------

async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await db.ensure_user(update.effective_user.id)
    products = await db.get_all_products(active_only=True)
    if not products:
        await update.message.reply_text("🏪 The shop is currently empty. Check back later!")
        return
    await update.message.reply_text(
        "🛍 <b>Shop</b>\n\nSelect a product to view its details:",
        parse_mode="HTML",
        reply_markup=shop_products_keyboard(products),
    )


async def shop_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product    = await db.get_product(product_id)
    if not product or not product["is_active"]:
        try:
            await query.edit_message_text("❌ This product is no longer available.")
        except BadRequest:
            pass
        return
    rate        = await db.get_currency_rate()
    final_price = int(product["base_currency_price"] * rate) + product["admin_profit"]
    flags       = []
    if product["requires_telegram_id"]:
        flags.append("📱 Telegram username")
    if product["requires_email"]:
        flags.append("📧 Email address")
    if product["requires_password"]:
        flags.append("🔑 Account password")
    flags_text = "\n".join(f"  • {f}" for f in flags) if flags else "  None"
    text = (
        f"📦 <b>{html.escape(product['name'])}</b>\n\n"
        f"💰 Price: <b>{final_price:,} Tomans</b>\n\n"
        f"📋 Required info from you:\n{flags_text}"
    )
    try:
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=product_buy_keyboard(product_id)
        )
    except BadRequest:
        pass


async def shop_back_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query    = update.callback_query
    await query.answer()
    products = await db.get_all_products(active_only=True)
    if not products:
        try:
            await query.edit_message_text("🏪 The shop is currently empty. Check back later!")
        except BadRequest:
            pass
        return
    try:
        await query.edit_message_text(
            "🛍 <b>Shop</b>\n\nSelect a product to view its details:",
            parse_mode="HTML",
            reply_markup=shop_products_keyboard(products),
        )
    except BadRequest:
        pass


# ---------------------------------------------------------------------------
# Checkout ConversationHandler — input collection
# ---------------------------------------------------------------------------

async def buy_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query      = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product    = await db.get_product(product_id)
    if not product or not product["is_active"]:
        try:
            await query.edit_message_text("❌ This product is no longer available.")
        except BadRequest:
            pass
        return ConversationHandler.END
    rate        = await db.get_currency_rate()
    final_price = int(product["base_currency_price"] * rate) + product["admin_profit"]
    context.user_data[_CTX_ORDER] = {
        "product_id":         product_id,
        "product_name":       product["name"],
        "base_price":         final_price,
        "final_price":        final_price,
        "discount_pct":       0,
        "input_telegram_id":  None,
        "input_email":        None,
        "input_password":     None,
        "requires_telegram_id": bool(product["requires_telegram_id"]),
        "requires_email":       bool(product["requires_email"]),
        "requires_password":    bool(product["requires_password"]),
    }
    return await _advance(query.message, context)


async def shop_get_tg_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_CTX_ORDER]["input_telegram_id"] = update.message.text.strip()
    return await _advance(update.message, context)


async def shop_get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_CTX_ORDER]["input_email"] = update.message.text.strip()
    return await _advance(update.message, context)


async def shop_get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_CTX_ORDER]["input_password"] = update.message.text.strip()
    return await _advance(update.message, context)


# ---------------------------------------------------------------------------
# Checkout — invoice action handlers (discount / pay-card / pay-wallet / cancel)
# ---------------------------------------------------------------------------

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
    code     = update.message.text.strip()
    discount = await db.get_discount(code)
    if not discount:
        await update.message.reply_text(
            "❌ Invalid or expired discount code. Try a different code or press Cancel on the invoice."
        )
        return COLLECT_DISCOUNT

    order    = context.user_data[_CTX_ORDER]
    pct      = discount["percentage_discount"]
    new_price = int(order["base_price"] * (1 - pct / 100))
    order["final_price"]  = new_price
    order["discount_pct"] = pct

    await update.message.reply_text(
        f"✅ Discount code <code>{html.escape(code)}</code> applied! "
        f"<b>{pct}%</b> off → new price: <b>{new_price:,} Tomans</b>",
        parse_mode="HTML",
    )
    return await _show_invoice(update.message, context)


async def shop_pay_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped '💳 Pay with Card' on the invoice."""
    query = update.callback_query
    await query.answer()
    order = context.user_data.get(_CTX_ORDER)
    if not order:
        await query.answer("Session expired. Please start over.", show_alert=True)
        return ConversationHandler.END
    ok = await _send_card_and_ask_receipt(query.message, context, order["final_price"])
    if not ok:
        return ConversationHandler.END
    return COLLECT_RECEIPT


async def shop_collect_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User sent a receipt photo for a card order payment."""
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a <b>photo</b> of your receipt.", parse_mode="HTML")
        return COLLECT_RECEIPT

    order    = context.user_data.get(_CTX_ORDER)
    if not order:
        await update.message.reply_text("❌ Session expired. Please start over.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    user_id  = update.effective_user.id
    photo_id = update.message.photo[-1].file_id

    # Create the order record with PENDING_PAYMENT status
    order_id = await db.create_order(
        user_id            = user_id,
        product_id         = order["product_id"],
        final_price_paid   = order["final_price"],
        payment_method     = "CARD_TRANSFER",
        input_telegram_id  = order.get("input_telegram_id"),
        input_email        = order.get("input_email"),
        input_password     = order.get("input_password"),
        status             = "PENDING_PAYMENT",
    )

    # Save receipt as a transaction linked to the order so admin can review
    tx_id = await db.create_transaction(
        user_id          = user_id,
        amount           = order["final_price"],
        receipt_photo_id = photo_id,
        order_id         = order_id,
    )

    context.user_data.pop(_CTX_ORDER, None)

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
    for admin_id in _get_admin_ids():
        try:
            await context.bot.send_photo(
                chat_id   = admin_id,
                photo     = photo_id,
                caption   = admin_caption,
                parse_mode= "HTML",
                reply_markup = receipt_sent_keyboard(order_id),
            )
        except Exception:
            logger.warning("Could not notify admin %s about order %s.", admin_id, order_id)

    return ConversationHandler.END


async def shop_pay_wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped '💰 Pay from Wallet' on the invoice."""
    query = update.callback_query
    order = context.user_data.get(_CTX_ORDER)
    if not order:
        await query.answer()
        await query.message.reply_text("❌ Session expired. Please start over.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    user_id     = update.effective_user.id
    user        = await db.get_user(user_id)
    wallet      = user["wallet_balance"] if user else 0
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
        user_id           = user_id,
        product_id        = order["product_id"],
        final_price_paid  = final_price,
        payment_method    = "WALLET",
        input_telegram_id = order.get("input_telegram_id"),
        input_email       = order.get("input_email"),
        input_password    = order.get("input_password"),
        status            = "PROCESSING",
    )
    context.user_data.pop(_CTX_ORDER, None)

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
        chat_id      = user_id,
        text         = "👇 Main menu:",
        reply_markup = main_menu_keyboard(),
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
    for admin_id in _get_admin_ids():
        try:
            await context.bot.send_message(
                chat_id      = admin_id,
                text         = admin_text,
                parse_mode   = "HTML",
                reply_markup = order_review_keyboard(order_id),
            )
        except Exception:
            logger.warning("Could not notify admin %s about wallet order %s.", admin_id, order_id)
    return ConversationHandler.END


async def shop_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inline '❌ Cancel' button on the invoice."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop(_CTX_ORDER, None)
    try:
        await query.edit_message_text("❌ Order cancelled.")
    except BadRequest:
        pass
    await context.bot.send_message(
        chat_id      = query.message.chat_id,
        text         = "👇 Use the menu below to continue.",
        reply_markup = main_menu_keyboard(),
    )
    return ConversationHandler.END


async def shop_force_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/cancel command fallback during input collection."""
    context.user_data.pop(_CTX_ORDER, None)
    await update.message.reply_text("❌ Order cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def _shop_conv_menu_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User pressed a main-menu button while inside the conversation — exit gracefully."""
    context.user_data.pop(_CTX_ORDER, None)
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


# ---------------------------------------------------------------------------
# Wallet — menu, top-up ConversationHandler
# ---------------------------------------------------------------------------

async def wallet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the '💰 My Wallet' ReplyKeyboard button."""
    user_id = update.effective_user.id
    await db.ensure_user(user_id)
    user    = await db.get_user(user_id)
    wallet  = user["wallet_balance"] if user else 0
    await update.message.reply_text(
        f"💰 <b>My Wallet</b>\n\nCurrent balance: <b>{wallet:,} Tomans</b>\n\n"
        "What would you like to do?",
        parse_mode="HTML",
        reply_markup=wallet_menu_keyboard(),
    )


async def wallet_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for wallet top-up: ask for the amount."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "➕ <b>Top-up Wallet</b>\n\nEnter the amount in Tomans you want to add to your wallet:",
        parse_mode="HTML",
    )
    return TOPUP_AMOUNT


async def topup_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect the top-up amount, then show the card + ask for receipt."""
    try:
        amount = int(update.message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid positive integer amount:")
        return TOPUP_AMOUNT

    context.user_data[_CTX_TOPUP] = {"amount": amount}
    ok = await _send_card_and_ask_receipt(update.message, context, amount)
    if not ok:
        context.user_data.pop(_CTX_TOPUP, None)
        return ConversationHandler.END
    return TOPUP_RECEIPT


async def topup_collect_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User sent a receipt photo for a wallet top-up."""
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a <b>photo</b> of your receipt.", parse_mode="HTML")
        return TOPUP_RECEIPT

    topup   = context.user_data.get(_CTX_TOPUP)
    if not topup:
        await update.message.reply_text("❌ Session expired. Please start over.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    user_id  = update.effective_user.id
    photo_id = update.message.photo[-1].file_id
    amount   = topup["amount"]

    tx_id = await db.create_transaction(
        user_id          = user_id,
        amount           = amount,
        receipt_photo_id = photo_id,
    )
    context.user_data.pop(_CTX_TOPUP, None)

    await update.message.reply_text(
        f"✅ Receipt received! Your top-up request of <b>{amount:,} Tomans</b> "
        f"(Transaction #{tx_id}) is pending admin approval.\n"
        "You will be notified once it is confirmed.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    # Notify all admins
    caption = (
        f"💰 <b>Wallet Top-up Request</b>\n\n"
        f"Transaction #{tx_id}\n"
        f"User: <code>{user_id}</code>\n"
        f"Amount: {amount:,} T"
    )
    for admin_id in _get_admin_ids():
        try:
            await context.bot.send_photo(
                chat_id      = admin_id,
                photo        = photo_id,
                caption      = caption,
                parse_mode   = "HTML",
                reply_markup = topup_receipt_keyboard(tx_id),
            )
        except Exception:
            logger.warning("Could not notify admin %s about top-up tx %s.", admin_id, tx_id)

    return ConversationHandler.END


async def topup_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline '❌ Cancel' on the top-up flow."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop(_CTX_TOPUP, None)
    try:
        await query.edit_message_text("❌ Top-up cancelled.")
    except BadRequest:
        pass
    await context.bot.send_message(
        chat_id      = query.message.chat_id,
        text         = "👇 Use the menu below to continue.",
        reply_markup = main_menu_keyboard(),
    )


async def wallet_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show order history from the wallet menu."""
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    orders  = await db.get_user_orders(user_id)

    status_map = {
        "PENDING_PAYMENT": "⏳ Pending Payment",
        "PROCESSING":      "🔄 Processing",
        "COMPLETED":       "✅ Completed",
        "REJECTED":        "❌ Rejected",
    }

    if not orders:
        try:
            await query.edit_message_text("📜 You have no orders yet.")
        except BadRequest:
            pass
        return

    lines = ["📜 <b>Order History</b>\n"]
    for o in orders[:20]:
        status = status_map.get(o["status"], o["status"])
        lines.append(
            f"• <b>{html.escape(o['product_name'])}</b> — "
            f"{o['final_price_paid']:,} T — {status}"
        )
    text = "\n".join(lines)
    try:
        await query.edit_message_text(text, parse_mode="HTML")
    except BadRequest:
        pass


# ---------------------------------------------------------------------------
# Profile & Support
# ---------------------------------------------------------------------------

async def user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await db.ensure_user(user_id)
    user    = await db.get_user(user_id)
    wallet  = user["wallet_balance"] if user else 0
    orders  = await db.get_user_orders(user_id)

    status_map = {
        "PENDING_PAYMENT": "⏳ Pending Payment",
        "PROCESSING":      "🔄 Processing",
        "COMPLETED":       "✅ Completed",
        "REJECTED":        "❌ Rejected",
    }

    text = f"👤 <b>Your Profile</b>\n\n💰 Wallet Balance: <b>{wallet:,} Tomans</b>\n"

    if not orders:
        text += "\n📋 You have no orders yet."
    else:
        recent  = orders[:10]
        text   += f"\n📋 <b>Recent Orders</b> (last {len(recent)}):\n"
        for o in recent:
            status = status_map.get(o["status"], o["status"])
            text  += f"\n• <b>{html.escape(o['product_name'])}</b> — {o['final_price_paid']:,} T — {status}"

    await update.message.reply_text(text, parse_mode="HTML")


async def user_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎧 <b>Support</b>\n\n"
        "If you have any questions or issues, please reach out to our support team:\n\n"
        "📩 @YourSupportHandle",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# ConversationHandler builders
# ---------------------------------------------------------------------------

def build_shop_conv() -> ConversationHandler:
    """
    Checkout conversation.
    Entry: shop_buy_<id>  (CallbackQuery)
    States handle input collection AND payment steps triggered by inline buttons.
    """
    menu_exit = MessageHandler(
        filters.Regex(r"^(🛍 Shop|👤 My Profile|💰 My Wallet|🎧 Support)$"),
        _shop_conv_menu_exit,
    )
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(buy_now_callback, pattern=r"^shop_buy_\d+$"),
        ],
        states={
            COLLECT_TG_ID:    [MessageHandler(filters.TEXT & ~filters.COMMAND, shop_get_tg_id)],
            COLLECT_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, shop_get_email)],
            COLLECT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, shop_get_password)],
            COLLECT_DISCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, shop_collect_discount)],
            COLLECT_RECEIPT:  [MessageHandler(filters.PHOTO, shop_collect_receipt)],
            CHECKOUT: [
                CallbackQueryHandler(shop_discount_callback,   pattern=r"^shop_discount$"),
                CallbackQueryHandler(shop_pay_card_callback,   pattern=r"^shop_pay_card$"),
                CallbackQueryHandler(shop_pay_wallet_callback, pattern=r"^shop_pay_wallet$"),
                CallbackQueryHandler(shop_cancel_callback,     pattern=r"^shop_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", shop_force_cancel),
            CallbackQueryHandler(shop_cancel_callback, pattern=r"^shop_cancel$"),
            menu_exit,
        ],
        allow_reentry=True,
    )


def build_topup_conv() -> ConversationHandler:
    """Wallet top-up conversation. Entry: wallet_topup (CallbackQuery)."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(wallet_topup_callback, pattern="^wallet_topup$"),
        ],
        states={
            TOPUP_AMOUNT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, topup_get_amount)],
            TOPUP_RECEIPT: [MessageHandler(filters.PHOTO, topup_collect_receipt)],
        },
        fallbacks=[
            CommandHandler("cancel", shop_force_cancel),
        ],
        allow_reentry=True,
    )

"""
handlers/shop/wallet.py — Wallet menu, top-up, and order history handlers.

Top-up conversation:
    topup_pay_card_callback → TOPUP_AMOUNT → TOPUP_RECEIPT → admin notified
"""

import html
import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ConversationHandler, ContextTypes

import database as db
from keyboards import (
    main_menu_keyboard,
    wallet_menu_keyboard,
    topup_receipt_keyboard,
)
from handlers.utils import get_admin_ids
from handlers.shop._helpers import CTX_TOPUP, TOPUP_AMOUNT, TOPUP_RECEIPT, send_card_and_ask_receipt

logger = logging.getLogger(__name__)


# ── Wallet menu ──────────────────────────────────────────────────────────────

async def wallet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the '💰 My Wallet' ReplyKeyboard button."""
    user_id = update.effective_user.id
    await db.ensure_user(user_id)
    user = await db.get_user(user_id)
    wallet = user["wallet_balance"] if user else 0
    await update.message.reply_text(
        f"💰 <b>My Wallet</b>\n\nCurrent balance: <b>{wallet:,} Tomans</b>\n\n"
        "What would you like to do?",
        parse_mode="HTML",
        reply_markup=wallet_menu_keyboard(),
    )


# ── Top-up conversation handlers ────────────────────────────────────────────

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

    context.user_data[CTX_TOPUP] = {"amount": amount}
    ok = await send_card_and_ask_receipt(update.message, context, amount)
    if not ok:
        context.user_data.pop(CTX_TOPUP, None)
        return ConversationHandler.END
    return TOPUP_RECEIPT


async def topup_collect_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User sent a receipt photo for a wallet top-up."""
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a <b>photo</b> of your receipt.", parse_mode="HTML")
        return TOPUP_RECEIPT

    topup = context.user_data.get(CTX_TOPUP)
    if not topup:
        await update.message.reply_text("❌ Session expired. Please start over.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    user_id = update.effective_user.id
    photo_id = update.message.photo[-1].file_id
    amount = topup["amount"]

    tx_id = await db.create_transaction(
        user_id=user_id,
        amount=amount,
        receipt_photo_id=photo_id,
    )
    context.user_data.pop(CTX_TOPUP, None)

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
    for admin_id in get_admin_ids():
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=photo_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=topup_receipt_keyboard(tx_id),
            )
        except Exception:
            logger.warning("Could not notify admin %s about top-up tx %s.", admin_id, tx_id)

    return ConversationHandler.END


async def topup_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline '❌ Cancel' on the top-up flow."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop(CTX_TOPUP, None)
    try:
        await query.edit_message_text("❌ Top-up cancelled.")
    except BadRequest:
        pass
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="👇 Use the menu below to continue.",
        reply_markup=main_menu_keyboard(),
    )


# ── Order history ────────────────────────────────────────────────────────────

async def wallet_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show order history from the wallet menu."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    orders = await db.get_user_orders(user_id)

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

"""
handlers/admin/transactions.py — Transaction review and order management handlers.
"""

import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from keyboards import (
    admin_main_menu_keyboard,
    transaction_review_keyboard,
    order_review_keyboard,
    order_payment_review_keyboard,
    receipt_sent_keyboard,
)
from handlers.utils import admin_filter

logger = logging.getLogger(__name__)


# ── Pending wallet top-up transactions ───────────────────────────────────────

async def pending_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all pending wallet top-up transactions."""
    if not admin_filter(update):
        return
    transactions = await db.get_pending_transactions()
    if not transactions:
        await update.message.reply_text(
            "✅ No pending transactions.", reply_markup=admin_main_menu_keyboard()
        )
        return
    for tx in transactions:
        is_card_order = tx.get("order_id") is not None
        if is_card_order:
            product_name = tx.get("product_name") or "Unknown Product"
            text = (
                f"💳 *Card Order Receipt #{tx['transaction_id']}*\n"
                f"User: `{tx['user_id']}`\n"
                f"Product: {product_name}\n"
                f"Amount: {tx['amount']:,} T\n"
                f"Date: {tx['created_at']}"
            )
            keyboard = receipt_sent_keyboard(tx["order_id"])
        else:
            text = (
                f"💰 *Wallet Top-up #{tx['transaction_id']}*\n"
                f"User: `{tx['user_id']}`\n"
                f"Amount: {tx['amount']:,} T\n"
                f"Date: {tx['created_at']}"
            )
            keyboard = transaction_review_keyboard(tx["transaction_id"])

        if tx["receipt_photo_id"]:
            await update.message.reply_photo(
                photo=tx["receipt_photo_id"],
                caption=text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )


async def transaction_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tx_id = int(query.data.split("_")[-1])
    tx = await db.get_transaction(tx_id)
    if not tx or tx["status"] != "PENDING":
        await query.edit_message_caption("⚠️ Transaction already processed.")
        return
    await db.update_transaction_status(tx_id, "APPROVED")
    await db.update_wallet(tx["user_id"], tx["amount"])
    await query.edit_message_caption(
        f"✅ Transaction #{tx_id} approved. {tx['amount']:,} T added to user {tx['user_id']}'s wallet."
    )
    # Notify the user
    try:
        await context.bot.send_message(
            chat_id=tx["user_id"],
            text=f"✅ Your wallet top-up of *{tx['amount']:,} T* has been approved!",
            parse_mode="Markdown",
        )
    except Exception:
        logger.warning("Could not notify user %s about approved transaction.", tx["user_id"])


async def transaction_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tx_id = int(query.data.split("_")[-1])
    tx = await db.get_transaction(tx_id)
    if not tx or tx["status"] != "PENDING":
        await query.edit_message_caption("⚠️ Transaction already processed.")
        return
    await db.update_transaction_status(tx_id, "REJECTED")
    await query.edit_message_caption(f"❌ Transaction #{tx_id} rejected.")
    try:
        await context.bot.send_message(
            chat_id=tx["user_id"],
            text="❌ Your wallet top-up receipt was rejected. Please contact support.",
        )
    except Exception:
        logger.warning("Could not notify user %s about rejected transaction.", tx["user_id"])


# ── Active (PROCESSING) orders ───────────────────────────────────────────────

async def processing_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all orders that are in PROCESSING state (paid, awaiting manual fulfillment)."""
    if not admin_filter(update):
        return
    orders = await db.get_orders_by_status("PROCESSING")
    if not orders:
        await update.message.reply_text(
            "✅ No active orders.", reply_markup=admin_main_menu_keyboard()
        )
        return
    for order in orders:
        details = []
        if order.get("input_telegram_id"):
            details.append(f"Telegram ID: <code>{html.escape(str(order['input_telegram_id']))}</code>")
        if order.get("input_email"):
            details.append(f"Email: <code>{html.escape(str(order['input_email']))}</code>")
        if order.get("input_password"):
            details.append(f"Password: <code>{html.escape(str(order['input_password']))}</code>")
        details_text = "\n".join(details) if details else "No extra details."
        text = (
            f"📋 <b>Order #{order['order_id']}</b>\n"
            f"Product: {html.escape(str(order['product_name']))}\n"
            f"User: <code>{order['user_id']}</code>\n"
            f"Paid: {order['final_price_paid']:,} T\n"
            f"Method: {order['payment_method']}\n"
            f"Date: {order['created_at']}\n\n"
            f"{details_text}"
        )
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=order_review_keyboard(order["order_id"]),
        )


async def order_complete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = await db.get_order(order_id)
    if not order:
        await query.edit_message_text("Order not found.")
        return
    await db.update_order_status(order_id, "COMPLETED")
    await query.edit_message_text(f"✅ Order #{order_id} marked as COMPLETED.")
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"🎉 Your order #{order_id} has been *completed*! Thank you.",
            parse_mode="Markdown",
        )
    except Exception:
        logger.warning("Could not notify user %s about completed order.", order["user_id"])


async def order_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = await db.get_order(order_id)
    if not order:
        await query.edit_message_text("Order not found.")
        return
    await db.update_order_status(order_id, "REJECTED")
    # Also mark the linked receipt transaction as REJECTED
    await db.update_transaction_status_by_order(order_id, "REJECTED")
    await query.edit_message_text(f"❌ Order #{order_id} rejected.")
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"❌ Your order #{order_id} has been rejected. Please contact support.",
        )
    except Exception:
        logger.warning("Could not notify user %s about rejected order.", order["user_id"])


async def order_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a PENDING_PAYMENT card order → move it to PROCESSING."""
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = await db.get_order(order_id)
    if not order:
        await query.edit_message_text("Order not found.")
        return
    await db.update_order_status(order_id, "PROCESSING")
    # Also mark the linked receipt transaction as APPROVED so it doesn't linger as PENDING
    await db.update_transaction_status_by_order(order_id, "APPROVED")
    try:
        await query.edit_message_caption(
            f"✅ Payment for Order #{order_id} approved. Status → PROCESSING."
        )
    except Exception:
        # Message might not have a caption (e.g. already edited)
        pass
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"✅ Your payment for order #{order_id} has been verified. We are now processing your order!",
        )
    except Exception:
        logger.warning("Could not notify user %s about approved order.", order["user_id"])

"""
handlers/admin/transactions.py — Transaction review and order management handlers.
"""

import html
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

import database as db
from keyboards import (
    admin_main_menu_keyboard,
    transaction_review_keyboard,
    order_review_keyboard,
    order_payment_review_keyboard,
    receipt_sent_keyboard,
    rejection_reason_keyboard,
    REJECTION_PREDEFINED_REASONS,
)
from handlers.utils import admin_filter, fmt_datetime
from handlers.admin._helpers import require_admin_callback

logger = logging.getLogger(__name__)

_INVALID_ORDER_TRANSITION_TEXT = "⚠️ وضعیت این مورد قبلاً تغییر کرده است."

# State for the custom-reason ConversationHandler
REJECTION_CUSTOM_REASON = 100


# ── Shared helper ────────────────────────────────────────────────────────────

async def _edit_message(
    query,
    text: str,
    reply_markup=None,
    parse_mode: Optional[str] = None,
) -> None:
    """Edit a message's caption if it has one, otherwise edit its text."""
    try:
        await query.edit_message_caption(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )
    except BadRequest:
        try:
            await query.edit_message_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
        except BadRequest:
            pass


# ── Pending wallet top-up transactions ───────────────────────────────────────

async def pending_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all pending wallet top-up transactions."""
    if not admin_filter(update):
        return
    transactions = await db.get_pending_transactions()
    if not transactions:
        await update.message.reply_text(
            "✅ هیچ تراکنش در انتظاری وجود ندارد.", reply_markup=admin_main_menu_keyboard()
        )
        return
    for tx in transactions:
        is_card_order = tx.get("order_id") is not None
        if is_card_order:
            product_name = tx.get("product_name") or "محصول نامشخص"
            count_line = f"\n🔢 تعداد: {tx['input_count']:,}" if tx.get("input_count") else ""
            text = (
                f"💳 *رسید سفارش کارتی #{tx['transaction_id']}*\n\n"
                f"👤 کاربر: `{tx['user_id']}`\n"
                f"📦 محصول: {product_name}\n"
                f"💰 مبلغ: {tx['amount']:,} تومان{count_line}\n"
                f"📅 تاریخ: {fmt_datetime(tx['created_at'])}"
            )
            keyboard = receipt_sent_keyboard(tx["order_id"])
        else:
            text = (
                f"💰 *شارژ کیف پول #{tx['transaction_id']}*\n\n"
                f"👤 کاربر: `{tx['user_id']}`\n"
                f"💵 مبلغ: {tx['amount']:,} تومان\n"
                f"📅 تاریخ: {fmt_datetime(tx['created_at'])}"
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
    if not await require_admin_callback(update):
        return
    await query.answer()
    tx_id = int(query.data.split("_")[-1])
    tx = await db.approve_wallet_topup_transaction(tx_id)
    if not tx:
        await _edit_message(query, "⚠️ این تراکنش قبلاً بررسی شده است.")
        return
    await _edit_message(
        query,
        f"✅ تراکنش #{tx_id} تایید شد. مبلغ {tx['amount']:,} تومان به کیف پول کاربر {tx['user_id']} اضافه شد.",
    )
    # Notify the user
    try:
        await context.bot.send_message(
            chat_id=tx["user_id"],
            text=f"✅ درخواست شارژ کیف پول شما به مبلغ *{tx['amount']:,} تومان* تایید شد!",
            parse_mode="Markdown",
        )
    except Exception:
        logger.warning("Could not notify user %s about approved transaction.", tx["user_id"])


async def transaction_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 1 for wallet top-up rejection — show reason selection keyboard."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    tx_id = int(query.data.split("_")[-1])
    await _edit_message(
        query,
        "📋 *دلیل رد این تراکنش را انتخاب کنید:*",
        reply_markup=rejection_reason_keyboard("t", tx_id),
        parse_mode="Markdown",
    )


# ── Active (PROCESSING) orders ───────────────────────────────────────────────

async def processing_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all orders that are in PROCESSING state (paid, awaiting manual fulfillment)."""
    if not admin_filter(update):
        return
    orders = await db.get_orders_by_status("PROCESSING")
    if not orders:
        await update.message.reply_text(
            "✅ هیچ سفارش فعالی وجود ندارد.", reply_markup=admin_main_menu_keyboard()
        )
        return
    for order in orders:
        details = []
        if order.get("input_count"):
            details.append(f"🔢 تعداد: <code>{order['input_count']:,}</code>")
        if order.get("input_telegram_id"):
            details.append(f"آیدی تلگرام: <code>{html.escape(str(order['input_telegram_id']))}</code>")
        if order.get("input_email"):
            details.append(f"ایمیل: <code>{html.escape(str(order['input_email']))}</code>")
        if order.get("input_password"):
            details.append(f"رمز عبور: <code>{html.escape(str(order['input_password']))}</code>")
        details_text = "\n".join(details) if details else "بدون جزئیات اضافی."
        text = (
            f"📋 <b>سفارش #{order['order_id']}</b>\n"
            f"محصول: {html.escape(str(order['product_name']))}\n"
            f"کاربر: <code>{order['user_id']}</code>\n"
            f"پرداخت شده: {order['final_price_paid']:,} تومان\n"
            f"روش پرداخت: {order['payment_method']}\n"
            f"تاریخ: {fmt_datetime(order['created_at'])}\n\n"
            f"{details_text}"
        )
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=order_review_keyboard(order["order_id"]),
        )


async def order_complete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = await db.transition_order_status(order_id, ("PROCESSING",), "COMPLETED")
    if not order:
        await _edit_message(query, _INVALID_ORDER_TRANSITION_TEXT)
        return
    await _edit_message(query, f"✅ سفارش #{order_id} به عنوان تکمیل شده ثبت شد.")
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"🎉 سفارش شما به شماره #{order_id} با موفقیت *تکمیل شد*! با تشکر از خرید شما.",
            parse_mode="Markdown",
        )
    except Exception:
        logger.warning("Could not notify user %s about completed order.", order["user_id"])


async def order_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 1 for processing-order rejection — show reason selection keyboard."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    await _edit_message(
        query,
        "📋 *دلیل رد این سفارش را انتخاب کنید:*",
        reply_markup=rejection_reason_keyboard("o", order_id),
        parse_mode="Markdown",
    )


async def order_payment_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 1 for card-payment order rejection — show reason selection keyboard."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    await _edit_message(
        query,
        "📋 *دلیل رد این پرداخت را انتخاب کنید:*",
        reply_markup=rejection_reason_keyboard("op", order_id),
        parse_mode="Markdown",
    )


async def order_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a PENDING_PAYMENT card order → move it to PROCESSING."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = await db.transition_order_status(
        order_id,
        ("PENDING_PAYMENT",),
        "PROCESSING",
        linked_transaction_status="APPROVED",
    )
    if not order:
        await _edit_message(query, _INVALID_ORDER_TRANSITION_TEXT)
        return
    await _edit_message(query, f"✅ پرداخت سفارش #{order_id} تایید شد. وضعیت → در حال پردازش.")
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"✅ پرداخت شما برای سفارش #{order_id} تایید شد. سفارش شما در حال آماده‌سازی است!",
        )
    except Exception:
        logger.warning("Could not notify user %s about approved order.", order["user_id"])


# ── Rejection reason selection ───────────────────────────────────────────────

async def _execute_rejection(
    reject_type: str,
    entity_id: int,
    reason: Optional[str],
    context: ContextTypes.DEFAULT_TYPE,
) -> str:
    """Perform DB rejection and notify the user. Returns admin confirmation text."""
    if reject_type == "t":
        tx = await db.reject_wallet_topup_transaction(entity_id, rejection_reason=reason)
        if not tx:
            return "⚠️ این تراکنش قبلاً بررسی شده است."
        if reason:
            user_text = (
                f"❌ درخواست شارژ کیف پول شما رد شد.\n\n"
                f"📋 <b>دلیل:</b> {html.escape(reason)}"
            )
        else:
            user_text = "❌ درخواست شارژ کیف پول شما رد شد. لطفاً با پشتیبانی تماس بگیرید."
        admin_text = f"❌ تراکنش #{entity_id} رد شد."
        if reason:
            admin_text += f"\n📋 دلیل: {reason}"
        try:
            await context.bot.send_message(
                chat_id=tx["user_id"], text=user_text, parse_mode="HTML"
            )
        except Exception:
            logger.warning("Could not notify user %s about rejected transaction.", tx["user_id"])
        return admin_text

    if reject_type == "op":
        order = await db.transition_order_status(
            entity_id,
            ("PENDING_PAYMENT",),
            "REJECTED",
            linked_transaction_status="REJECTED",
            rejection_reason=reason,
        )
        if not order:
            return _INVALID_ORDER_TRANSITION_TEXT
        if reason:
            user_text = (
                f"❌ سفارش شما به شماره #{entity_id} رد شد.\n\n"
                f"📋 <b>دلیل:</b> {html.escape(reason)}"
            )
        else:
            user_text = (
                f"❌ سفارش شما به شماره #{entity_id} رد شد."
                " لطفاً برای پیگیری با پشتیبانی تماس بگیرید."
            )
        admin_text = f"❌ سفارش #{entity_id} (پرداخت کارتی) رد شد."
        if reason:
            admin_text += f"\n📋 دلیل: {reason}"
        try:
            await context.bot.send_message(
                chat_id=order["user_id"], text=user_text, parse_mode="HTML"
            )
        except Exception:
            logger.warning("Could not notify user %s about rejected order payment.", order["user_id"])
        return admin_text

    if reject_type == "o":
        order = await db.transition_order_status(
            entity_id,
            ("PROCESSING",),
            "REJECTED",
            refund_wallet_on_reject=True,
            rejection_reason=reason,
        )
        if not order:
            return _INVALID_ORDER_TRANSITION_TEXT
        is_wallet = order["payment_method"] == "WALLET"
        refund_line = (
            f"\n💰 مبلغ <b>{order['final_price_paid']:,} تومان</b> به کیف پول شما بازگشت داده شد."
            if is_wallet else ""
        )
        reason_line = f"\n\n📋 <b>دلیل:</b> {html.escape(reason)}" if reason else ""
        if reason or is_wallet:
            user_text = (
                f"❌ سفارش شما به شماره #{entity_id} رد شد."
                f"{refund_line}{reason_line}"
            )
        else:
            user_text = (
                f"❌ سفارش شما به شماره #{entity_id} رد شد."
                " لطفاً برای پیگیری با پشتیبانی تماس بگیرید."
            )
        admin_text = f"❌ سفارش #{entity_id} رد شد."
        if is_wallet:
            admin_text += f"\n💰 مبلغ {order['final_price_paid']:,} تومان به کیف پول بازگشت."
        if reason:
            admin_text += f"\n📋 دلیل: {reason}"
        try:
            await context.bot.send_message(
                chat_id=order["user_id"], text=user_text, parse_mode="HTML"
            )
        except Exception:
            logger.warning("Could not notify user %s about rejected order.", order["user_id"])
        return admin_text

    return "⚠️ نوع رد نامعتبر است."


async def rejection_reason_select_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles admin selecting a predefined reason (1-4) or skip (0) after clicking Reject."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()

    m = re.match(r"^admin_rr_(t|op|o)_(\d+)_(0|1|2|3|4)$", query.data)
    if not m:
        return
    reject_type, entity_id, code = m.group(1), int(m.group(2)), m.group(3)
    reason = REJECTION_PREDEFINED_REASONS.get(code)  # None when code == "0" (skip)

    admin_text = await _execute_rejection(reject_type, entity_id, reason, context)
    await _edit_message(query, admin_text)


async def rejection_custom_entry_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """ConversationHandler entry — admin chose to write a custom rejection reason."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()

    m = re.match(r"^admin_rr_(t|op|o)_(\d+)_c$", query.data)
    if not m:
        return ConversationHandler.END

    reject_type, entity_id = m.group(1), int(m.group(2))
    context.user_data["pending_rejection"] = {
        "type": reject_type,
        "id": entity_id,
        "chat_id": query.message.chat_id,
        "message_id": query.message.message_id,
    }

    # Remove the keyboard from the original message so admin can't double-click
    await _edit_message(query, "⏳ در انتظار دلیل رد...")
    await query.message.reply_text(
        "✏️ *دلیل رد را تایپ کنید:*\n\nبرای انصراف ❌ انصراف را بزنید.",
        parse_mode="Markdown",
        reply_markup=__import__("keyboards").cancel_keyboard(),
    )
    return REJECTION_CUSTOM_REASON


async def rejection_custom_receive(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receives the admin's typed custom rejection reason and performs the rejection."""
    reason = update.message.text.strip()
    pending = context.user_data.pop("pending_rejection", None)
    if not pending or not reason:
        await update.message.reply_text(
            "⚠️ عملیات رد لغو شد.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return ConversationHandler.END

    admin_text = await _execute_rejection(
        pending["type"], pending["id"], reason, context
    )
    # Update the original receipt/order message to show the final result
    try:
        await context.bot.edit_message_text(
            chat_id=pending["chat_id"],
            message_id=pending["message_id"],
            text=admin_text,
        )
    except BadRequest:
        try:
            await context.bot.edit_message_caption(
                chat_id=pending["chat_id"],
                message_id=pending["message_id"],
                caption=admin_text,
            )
        except BadRequest:
            pass

    await update.message.reply_text(
        "✅ رد با موفقیت انجام شد.",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


async def rejection_custom_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Fallback — admin cancelled writing a custom rejection reason."""
    context.user_data.pop("pending_rejection", None)
    # Restore the original message text to show cancellation
    await update.message.reply_text(
        "🚫 رد لغو شد.",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END

"""
handlers/admin/transactions.py — Transaction review and order management handlers.
"""

import html
import logging
from datetime import datetime, timezone, timedelta

from telegram import Update
from telegram.error import BadRequest
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
from handlers.admin._helpers import require_admin_callback

logger = logging.getLogger(__name__)

# Tehran is UTC+3:30 (fixed offset — no DST handling needed for display)
_TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
_INVALID_ORDER_TRANSITION_TEXT = "This order is no longer in a valid state for this action."


def _fmt_dt(raw: str) -> str:
    """Convert an ISO UTC datetime string to a beautiful Tehran-time string."""
    if not raw:
        return "—"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_teh = dt.astimezone(_TEHRAN_TZ)
        return dt_teh.strftime("%Y/%m/%d — ساعت %H:%M")
    except Exception:
        return raw


# ── Shared helper ────────────────────────────────────────────────────────────

async def _edit_message(query, text: str) -> None:
    """Edit a message's caption if it has one, otherwise edit its text."""
    try:
        await query.edit_message_caption(text)
    except BadRequest:
        try:
            await query.edit_message_text(text)
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
                f"📅 تاریخ: {_fmt_dt(tx['created_at'])}"
            )
            keyboard = receipt_sent_keyboard(tx["order_id"])
        else:
            text = (
                f"💰 *شارژ کیف پول #{tx['transaction_id']}*\n\n"
                f"👤 کاربر: `{tx['user_id']}`\n"
                f"💵 مبلغ: {tx['amount']:,} تومان\n"
                f"📅 تاریخ: {_fmt_dt(tx['created_at'])}"
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
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    tx_id = int(query.data.split("_")[-1])
    tx = await db.reject_wallet_topup_transaction(tx_id)
    if not tx:
        await _edit_message(query, "⚠️ این تراکنش قبلاً بررسی شده است.")
        return
    await _edit_message(query, f"❌ تراکنش #{tx_id} رد شد.")
    try:
        await context.bot.send_message(
            chat_id=tx["user_id"],
            text="❌ رسید پرداخت شما برای شارژ کیف پول رد شد. لطفاً با پشتیبانی تماس بگیرید.",
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
            f"تاریخ: {_fmt_dt(order['created_at'])}\n\n"
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
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = await db.transition_order_status(order_id, ("PROCESSING",), "REJECTED")
    if not order:
        await _edit_message(query, _INVALID_ORDER_TRANSITION_TEXT)
        return
    await _edit_message(query, f"❌ سفارش #{order_id} رد شد.")
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"❌ سفارش شما به شماره #{order_id} رد شد. لطفاً برای پیگیری با پشتیبانی تماس بگیرید.",
        )
    except Exception:
        logger.warning("Could not notify user %s about rejected order.", order["user_id"])


async def order_payment_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = await db.transition_order_status(
        order_id,
        ("PENDING_PAYMENT",),
        "REJECTED",
        linked_transaction_status="REJECTED",
    )
    if not order:
        await _edit_message(query, _INVALID_ORDER_TRANSITION_TEXT)
        return
    await _edit_message(query, f"❌ سفارش #{order_id} رد شد.")
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"❌ سفارش شما به شماره #{order_id} رد شد. لطفاً برای پیگیری با پشتیبانی تماس بگیرید.",
        )
    except Exception:
        logger.warning("Could not notify user %s about rejected order payment.", order["user_id"])


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

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
from handlers.utils import get_all_admin_ids, fmt_datetime
from handlers.shop._helpers import CTX_TOPUP, TOPUP_AMOUNT, TOPUP_RECEIPT, send_card_and_ask_receipt
from handlers.emoji import get_all_ces

logger = logging.getLogger(__name__)


# ── Wallet menu ──────────────────────────────────────────────────────────────

async def wallet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the '💰 My Wallet' ReplyKeyboard button."""
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
    ces = await get_all_ces()
    await update.message.reply_text(
        f"{ces['emoji_wallet']} <b>کیف پول من</b>\n\nموجودی فعلی: <b>{wallet:,} تومان</b>\n\n"
        "چه کاری می‌خواهید انجام دهید؟",
        parse_mode="HTML",
        reply_markup=wallet_menu_keyboard(),
    )


# ── Top-up conversation handlers ────────────────────────────────────────────

async def wallet_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for wallet top-up: ask for the amount with min/max limits displayed."""
    query = update.callback_query
    await query.answer()

    # Fetch current min/max limits
    min_amount = await db.get_min_topup_amount()
    max_amount = await db.get_max_topup_amount()

    # Format limit displays
    min_display = f"{min_amount:,} تومان" if min_amount > 0 else "بدون محدودیت"
    max_display = f"{max_amount:,} تومان" if max_amount > 0 else "بدون محدودیت"

    # Build compact, informative message
    limits_line = f"<b>حداقل شارژ:</b> {min_display} | <b>حداکثر شارژ:</b> {max_display}"
    message_text = (
        f"➕ <b>شارژ کیف پول</b>\n\n"
        f"{limits_line}\n\n"
        f"مبلغ مورد نظر را به <b>تومان</b> وارد کنید:"
    )

    await query.message.reply_text(message_text, parse_mode="HTML")
    return TOPUP_AMOUNT


async def topup_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect the top-up amount, then show the card + ask for receipt."""
    try:
        amount = int(update.message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد مثبت معتبر وارد کنید:")
        return TOPUP_AMOUNT

    min_amount = await db.get_min_topup_amount()
    if min_amount > 0 and amount < min_amount:
        await update.message.reply_text(
            f"❌ حداقل مبلغ شارژ کیف‌پول <b>{min_amount:,} تومان</b> است.\n"
            f"لطفاً مبلغی برابر یا بیشتر از این مقدار وارد کنید:",
            parse_mode="HTML",
        )
        return TOPUP_AMOUNT

    max_amount = await db.get_max_topup_amount()
    if max_amount > 0 and amount > max_amount:
        await update.message.reply_text(
            f"❌ حداکثر مبلغ شارژ کیف‌پول <b>{max_amount:,} تومان</b> است.\n"
            f"لطفاً مبلغی برابر یا کمتر از این مقدار وارد کنید:",
            parse_mode="HTML",
        )
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
        await update.message.reply_text("❌ لطفاً <b>عکس</b> رسید خود را ارسال کنید.", parse_mode="HTML")
        return TOPUP_RECEIPT

    topup = context.user_data.get(CTX_TOPUP)
    if not topup:
        await update.message.reply_text("❌ نشست شما به پایان رسیده است. لطفاً دوباره تلاش کنید.", reply_markup=main_menu_keyboard())
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
        f"✅ رسید دریافت شد! درخواست شارژ شما به مبلغ <b>{amount:,} تومان</b> "
        f"(تراکنش #{tx_id}) در انتظار تایید مدیریت است.\n"
        "پس از تایید، به شما اطلاع‌رسانی خواهد شد.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    # Notify all admins
    caption = (
        f"💰 <b>درخواست شارژ کیف پول</b>\n\n"
        f"تراکنش #{tx_id}\n"
        f"کاربر: <code>{user_id}</code>\n"
        f"مبلغ: {amount:,} تومان"
    )
    for admin_id in get_all_admin_ids():
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
        await query.edit_message_text("❌ شارژ لغو شد.")
    except BadRequest:
        pass
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="👇 از منوی زیر برای ادامه استفاده کنید.",
        reply_markup=main_menu_keyboard(),
    )


# ── Order history ────────────────────────────────────────────────────────────

async def wallet_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show wallet top-up history and order history from the wallet menu."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    orders = await db.get_user_orders(user_id)
    topups = await db.get_user_topup_transactions(user_id)

    if not orders and not topups:
        try:
            await query.edit_message_text("📜 شما هنوز هیچ سابقه‌ای ندارید.")
        except BadRequest:
            pass
        return

    status_map = {
        "PENDING_PAYMENT": "⏳ در انتظار پرداخت",
        "PROCESSING":      "🔄 در حال پردازش",
        "COMPLETED":       "✅ تکمیل شده",
        "REJECTED":        "❌ لغو شده",
    }

    lines = ["📜 <b>تاریخچه کیف پول</b>\n"]

    if topups:
        lines.append("💰 <b>شارژهای کیف پول</b>")
        for tx in topups[:10]:
            tx_date = fmt_datetime(tx.get("created_at", ""))
            lines.append(
                f"• +{tx['amount']:,} تومان\n"
                f"  📅 {tx_date}"
            )
        lines.append("")

    if orders:
        lines.append("📦 <b>سفارشات</b>")
        for o in orders[:10]:
            status = status_map.get(o["status"], o["status"])
            order_date = fmt_datetime(o.get("created_at", ""))
            lines.append(
                f"• <b>{html.escape(o['product_name'])}</b>\n"
                f"  💰 {o['final_price_paid']:,} تومان | {status}\n"
                f"  📅 {order_date}"
            )

    text = "\n".join(lines)
    try:
        await query.edit_message_text(text, parse_mode="HTML")
    except BadRequest:
        pass

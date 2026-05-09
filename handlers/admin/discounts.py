"""
handlers/admin/discounts.py — Discount management and conversation handler.

State machine:
    ADD_DISCOUNT: AD_CODE → AD_PERCENT → AD_MAX_USES → AD_EXPIRES_AT → (save)
"""

from typing import Optional

import aiosqlite
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from database import DB_PATH
from keyboards import (
    admin_main_menu_keyboard,
    discounts_list_keyboard,
    discount_detail_keyboard,
    cancel_keyboard,
    cancel_skip_keyboard,
    back_inline_keyboard,
)
from handlers.utils import admin_filter, fmt_datetime
from handlers.admin._helpers import CTX_DISCOUNT, cancel_conversation, require_admin_callback

# ── Conversation states ──────────────────────────────────────────────────────

AD_CODE = 30
AD_PERCENT = 31
AD_MAX_USES = 32
AD_EXPIRES_AT = 33

# Date format accepted from admin for expiry input
_DATE_FORMAT = "%Y-%m-%d"


# ── Discount list & detail ───────────────────────────────────────────────────

async def manage_discounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not admin_filter(update):
        return
    discounts = await db.get_all_discounts()
    text = "🏷 *مدیریت تخفیف‌ها*\n\nیک کد تخفیف را برای مدیریت انتخاب کنید یا کد جدیدی اضافه کنید."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=discounts_list_keyboard(discounts),
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=discounts_list_keyboard(discounts),
        )


async def discount_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    # callback_data = "admin_discount_view_<code>"
    code = "_".join(query.data.split("_")[3:])
    discount = await db.get_discount(code) or await _get_discount_any(code)
    if not discount:
        await query.edit_message_text("کد تخفیف یافت نشد.")
        return
    status = "✅ فعال" if discount["is_active"] else "❌ غیرفعال"
    pct = discount.get("percentage_discount", discount.get("amount", 0))
    use_count = discount.get("use_count", 0)
    max_uses = discount.get("max_uses", 0)
    expires_at = discount.get("expires_at")

    usage_line = (
        f"📊 استفاده شده: <b>{use_count}</b> / <b>{max_uses}</b>"
        if max_uses > 0
        else f"📊 استفاده شده: <b>{use_count}</b> بار (بدون سقف)"
    )
    expiry_line = (
        f"\n⏰ انقضا: <b>{expires_at[:10]}</b>"
        if expires_at
        else "\n⏰ انقضا: بدون تاریخ انقضا"
    )

    await query.edit_message_text(
        f"🏷 کد: <code>{discount['code']}</code>\n"
        f"تخفیف: <b>{pct}%</b>\n"
        f"وضعیت: {status}\n"
        f"{usage_line}"
        f"{expiry_line}",
        parse_mode="HTML",
        reply_markup=discount_detail_keyboard(code),
    )


async def _get_discount_any(code: str) -> Optional[dict]:
    """Fetch discount regardless of active status (for admin view), including use_count."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            """
            SELECT d.*,
                   (SELECT COUNT(*) FROM Orders o
                    WHERE o.discount_code = d.code
                      AND o.status != 'REJECTED') AS use_count
            FROM Discounts d WHERE d.code = ?
            """,
            (code,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def discount_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    # callback_data = "admin_discount_delete_<code>"
    code = "_".join(query.data.split("_")[3:])
    await db.delete_discount(code)
    await query.edit_message_text(
        "🗑 کد تخفیف حذف شد.",
        reply_markup=back_inline_keyboard("admin_discount_list"),
    )


# ── Add discount conversation ────────────────────────────────────────────────

async def add_discount_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_DISCOUNT] = {}
    await query.message.reply_text(
        "➕ *افزودن کد تخفیف*\n\nمرحله ۱/۴: *کد* تخفیف را وارد کنید (یک عبارت متنی):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AD_CODE


async def ad_get_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)
    code = update.message.text.strip()
    if not code:
        await update.message.reply_text("❌ کد نمی‌تواند خالی باشد. دوباره تلاش کنید:")
        return AD_CODE
    context.user_data[CTX_DISCOUNT]["code"] = code
    await update.message.reply_text(
        "مرحله ۲/۴: *درصد تخفیف* را وارد کنید (۱ تا ۱۰۰):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AD_PERCENT


async def ad_get_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)
    try:
        pct = int(update.message.text.strip())
        if not (1 <= pct <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ یک عدد صحیح بین ۱ تا ۱۰۰ وارد کنید:")
        return AD_PERCENT
    context.user_data[CTX_DISCOUNT]["pct"] = pct
    await update.message.reply_text(
        "مرحله ۳/۴: *حداکثر تعداد استفاده* را وارد کنید (اختیاری).\n"
        "عدد صحیح مثبت (مثلاً ۵۰) یا «⏭ رد کردن» برای نامحدود:",
        parse_mode="Markdown",
        reply_markup=cancel_skip_keyboard(),
    )
    return AD_MAX_USES


async def ad_get_max_uses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "❌ انصراف":
        return await cancel_conversation(update, context)
    if text == "⏭ رد کردن":
        context.user_data[CTX_DISCOUNT]["max_uses"] = 0
    else:
        try:
            max_uses = int(text)
            if max_uses <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ یک عدد صحیح مثبت وارد کنید یا «⏭ رد کردن» را بزنید:"
            )
            return AD_MAX_USES
        context.user_data[CTX_DISCOUNT]["max_uses"] = max_uses
    await update.message.reply_text(
        "مرحله ۴/۴: *تاریخ انقضا* را وارد کنید (اختیاری).\n"
        "فرمت: <code>YYYY-MM-DD</code> (مثال: <code>2026-12-31</code>)\n"
        "یا «⏭ رد کردن» برای بدون تاریخ انقضا:",
        parse_mode="HTML",
        reply_markup=cancel_skip_keyboard(),
    )
    return AD_EXPIRES_AT


async def ad_get_expires_at(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from datetime import datetime, timezone

    text = update.message.text.strip()
    if text == "❌ انصراف":
        return await cancel_conversation(update, context)

    expires_iso: Optional[str] = None
    if text != "⏭ رد کردن":
        try:
            parsed = datetime.strptime(text, _DATE_FORMAT)
            # Store as end-of-day UTC ISO string so the date is fully inclusive
            expires_iso = parsed.replace(hour=23, minute=59, second=59,
                                         tzinfo=timezone.utc).isoformat()
        except ValueError:
            await update.message.reply_text(
                "❌ فرمت تاریخ اشتباه است. لطفاً به شکل <code>YYYY-MM-DD</code> وارد کنید "
                "یا «⏭ رد کردن» را بزنید:",
                parse_mode="HTML",
            )
            return AD_EXPIRES_AT

    data = context.user_data.pop(CTX_DISCOUNT, {})
    code = data["code"]
    pct = data["pct"]
    max_uses = data.get("max_uses", 0)

    inserted = await db.add_discount(code, pct, max_uses=max_uses, expires_at=expires_iso)
    if inserted:
        limits = []
        if max_uses > 0:
            limits.append(f"سقف: {max_uses} بار")
        if expires_iso:
            limits.append(f"انقضا: {text}")
        limits_text = " · ".join(limits) if limits else "بدون محدودیت"
        await update.message.reply_text(
            f"✅ کد تخفیف <code>{code}</code> ({pct}%) با موفقیت اضافه شد.\n"
            f"📋 {limits_text}",
            parse_mode="HTML",
            reply_markup=admin_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"⚠️ کد تخفیف <code>{code}</code> از قبل وجود دارد و تغییری ایجاد نشد.",
            parse_mode="HTML",
            reply_markup=admin_main_menu_keyboard(),
        )
    return ConversationHandler.END

"""
handlers/admin/panel.py — Admin entry point and generic navigation callbacks.
"""

import html

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from keyboards import admin_main_menu_keyboard, user_list_pagination_keyboard
from handlers.utils import admin_filter, fmt_datetime
from handlers.admin._helpers import require_admin_callback

# Pagination constants
USERS_PER_PAGE = 10

# User lookup state keys
CTX_SEARCH_RESULTS = "user_search_results"
CTX_SEARCH_PAGE = "user_search_page"


def _format_user_card(user: dict) -> str:
    """Format a single user profile card in HTML (without order stats)."""
    user_id = user["user_id"]
    username_line = f"@{html.escape(user['username'])}" if user.get("username") else "—"
    first_name = html.escape(user.get("first_name") or "")
    last_name = html.escape(user.get("last_name") or "")
    full_name = f"{first_name} {last_name}".strip() or "—"
    lang = html.escape(user.get("language_code") or "—")

    return (
        f"👤 <b>اطلاعات کاربر</b>\n\n"
        f"🆔 آیدی: <code>{user_id}</code>\n"
        f"📛 نام: {full_name}\n"
        f"🔗 یوزرنیم: {username_line}\n"
        f"🌐 زبان: {lang}\n"
        f"📅 عضویت: {fmt_datetime(user.get('joined_at', ''))}\n\n"
        f"💰 <b>موجودی کیف پول: {user['wallet_balance']:,} تومان</b>"
    )


def _format_user_summary(user: dict) -> str:
    """Format a user as a one-liner for list views."""
    username_part = f"@{html.escape(user['username'])} " if user.get("username") else ""
    first_name = html.escape(user.get("first_name") or "")
    last_name = html.escape(user.get("last_name") or "")
    full_name = f"{first_name} {last_name}".strip() or "(بدون نام)"
    return f"🆔 <code>{user['user_id']}</code> | {username_part}{full_name} | 💰 {user['wallet_balance']:,}"


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point: /admin command — only visible to admins."""
    if not admin_filter(update):
        await update.message.reply_text("⛔ دسترسی غیرمجاز.")
        return
    tg_user = update.effective_user
    await db.ensure_user(
        tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        language_code=tg_user.language_code,
    )
    await update.message.reply_text(
        "👑 به پنل مدیریت خوش آمدید.",
        reply_markup=admin_main_menu_keyboard(),
    )


async def admin_back_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generic back-to-main callback."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    await query.edit_message_text(
        "👑 پنل مدیریت — یک گزینه را انتخاب کنید:",
        reply_markup=None,
    )


async def user_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Admin command: /user [query]
    Smart search supporting:
    - Numeric user ID: /user 123456789
    - Username search: /user @username or /user username
    - Name search: /user john (partial match on first/last name)
    - List all users: /user (no args, with pagination)
    """
    if not admin_filter(update):
        return

    args = context.args
    query_arg = args[0] if args else None

    # No args → show paginated list of all users
    if not query_arg:
        users, total = await db.get_all_users_paginated(offset=0, limit=USERS_PER_PAGE)
        if not users:
            await update.message.reply_text("❌ هیچ کاربری یافت نشد.")
            return

        text = f"👥 <b>لیست تمام کاربران ({total})</b>\n\n"
        text += "\n".join(_format_user_summary(u) for u in users)

        # Store results in context for pagination
        context.user_data[CTX_SEARCH_RESULTS] = users
        context.user_data[CTX_SEARCH_PAGE] = 0

        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=user_list_pagination_keyboard(0, USERS_PER_PAGE, total),
        )
        return

    # Numeric ID lookup
    if query_arg.isdigit():
        user_id = int(query_arg)
        user = await db.get_user(user_id)
        if not user:
            await update.message.reply_text(
                f"❌ کاربری با آیدی <code>{user_id}</code> یافت نشد.",
                parse_mode="HTML",
            )
            return

        orders = await db.get_user_orders(user_id)
        order_counts: dict[str, int] = {}
        for o in orders:
            order_counts[o["status"]] = order_counts.get(o["status"], 0) + 1

        text = _format_user_card(user)
        text += "\n\n📦 <b>سفارشات</b>\n"
        text += f"  ✅ تکمیل شده: {order_counts.get('COMPLETED', 0)}\n"
        text += f"  🔄 در حال پردازش: {order_counts.get('PROCESSING', 0)}\n"
        text += f"  ⏳ در انتظار پرداخت: {order_counts.get('PENDING_PAYMENT', 0)}\n"
        text += f"  ❌ لغو شده: {order_counts.get('REJECTED', 0)}\n"
        text += f"  📊 مجموع: {len(orders)}"

        await update.message.reply_text(text, parse_mode="HTML")
        return

    # Username search (with or without @)
    if query_arg.startswith("@"):
        username = query_arg[1:]
    else:
        username = query_arg

    user = await db.get_user_by_username(username)
    if user:
        text = _format_user_card(user)
        await update.message.reply_text(text, parse_mode="HTML")
        return

    # Name search (partial match)
    users = await db.search_users_by_name(query_arg, limit=50)
    if not users:
        await update.message.reply_text(
            f"❌ نتیجه‌ای برای جستجوی <code>{html.escape(query_arg)}</code> یافت نشد.",
            parse_mode="HTML",
        )
        return

    if len(users) == 1:
        # Single result → show full profile
        user = users[0]
        text = _format_user_card(user)
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        # Multiple results → show list with pagination
        text = f"🔍 <b>نتایج جستجو برای: {html.escape(query_arg)}</b> ({len(users)} نتیجه)\n\n"
        text += "\n".join(_format_user_summary(u) for u in users[:USERS_PER_PAGE])

        # Store results in context for pagination
        context.user_data[CTX_SEARCH_RESULTS] = users
        context.user_data[CTX_SEARCH_PAGE] = 0

        total = len(users)
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=user_list_pagination_keyboard(0, USERS_PER_PAGE, total),
        )


async def user_list_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pagination for user search results."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()

    # Parse offset from callback data: "user_list_page_0", "user_list_page_10", etc.
    offset = int(query.data.split("_")[-1])

    results = context.user_data.get(CTX_SEARCH_RESULTS, [])
    if not results:
        await query.edit_message_text("❌ نتایج جستجو منقضی شده است. دوباره جستجو کنید.")
        return

    # Get page of results
    end_idx = offset + USERS_PER_PAGE
    page_users = results[offset:end_idx]

    text = f"👥 <b>نتایج ({offset + 1}–{min(end_idx, len(results))} از {len(results)})</b>\n\n"
    text += "\n".join(_format_user_summary(u) for u in page_users)

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=user_list_pagination_keyboard(offset, USERS_PER_PAGE, len(results)),
    )

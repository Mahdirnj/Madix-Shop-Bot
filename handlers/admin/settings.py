"""
handlers/admin/settings.py — Settings panel: support handle & admin management.

Conversation state machine:
    SET_SUPPORT:  SS_HANDLE(60) → save
    ADD_ADMIN:    AA_ID(61) → AA_NAME(62) → save
"""

import html
import logging

from telegram import MessageEntity, Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    admin_main_menu_keyboard,
    admin_settings_keyboard,
    admin_list_keyboard,
    cancel_keyboard,
    emoji_slots_keyboard,
)
from handlers.utils import admin_filter, get_admin_ids, _db_admin_ids
from handlers.admin._helpers import cancel_conversation, require_admin_callback
from handlers.emoji import SLOTS, SLOT_LABELS

logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────

SS_HANDLE = 60   # waiting for new support handle text
AA_ID     = 61   # waiting for new admin's numeric Telegram ID
AA_NAME   = 62   # waiting for new admin's display name
SE_EMOJI  = 63   # waiting for a message containing a premium custom emoji

# Context keys
_CTX_NEW_ADMIN_ID   = "new_admin_id"
_CTX_EMOJI_SLOT     = "pending_emoji_slot"


# ── Settings menu ─────────────────────────────────────────────────────────────

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the settings inline menu (triggered by ⚙️ تنظیمات reply button)."""
    if not admin_filter(update):
        return
    current_handle = await db.get_setting("support_handle") or "تنظیم نشده"
    await update.message.reply_text(
        f"⚙️ <b>تنظیمات</b>\n\n"
        f"🎧 ایدی فعال پشتیبانی: <code>{html.escape(current_handle)}</code>",
        parse_mode="HTML",
        reply_markup=admin_settings_keyboard(),
    )


# ── Support handle management ─────────────────────────────────────────────────

async def settings_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin tapped 'Edit Support Handle' in settings inline menu."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    current = await db.get_setting("support_handle") or "تنظیم نشده"
    await query.message.reply_text(
        f"🎧 <b>ویرایش ایدی پشتیبانی</b>\n\n"
        f"مقدار فعلی: <code>{html.escape(current)}</code>\n\n"
        "هندل جدید را وارد کنید (مثلاً <code>@MySupport</code>):",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return SS_HANDLE


async def ss_get_handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the new support handle to the database."""
    handle = update.message.text.strip()
    if handle == "❌ انصراف":
        await update.message.reply_text(
            "❌ عملیات لغو شد.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return ConversationHandler.END
    await db.set_setting("support_handle", handle)
    await update.message.reply_text(
        f"✅ هندل پشتیبانی به <code>{html.escape(handle)}</code> تغییر یافت.",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ── Admin list ────────────────────────────────────────────────────────────────

async def admin_manage_admins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the list of admins with add/remove options."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    admins = await db.get_all_admins()
    env_ids = set(get_admin_ids())
    await query.message.reply_text(
        f"👥 <b>مدیریت ادمین‌ها</b>\n\n"
        f"تعداد ادمین‌های فعال: <b>{len(admins)}</b>\n"
        "ادمین‌های اصلی (🔐) قابل حذف نیستند.",
        parse_mode="HTML",
        reply_markup=admin_list_keyboard(admins, env_ids),
    )


async def remove_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a DB admin (env/master admins are blocked at keyboard level)."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    user_id = int(query.data.split("_")[-1])
    env_ids = set(get_admin_ids())
    if user_id in env_ids:
        await query.answer("⛔ ادمین اصلی قابل حذف نیست.", show_alert=True)
        return
    await db.remove_admin(user_id)
    # Update in-memory cache
    _db_admin_ids.discard(user_id)
    # Refresh the admin list view
    admins = await db.get_all_admins()
    try:
        await query.edit_message_reply_markup(admin_list_keyboard(admins, env_ids))
    except Exception:
        pass
    await query.answer(f"✅ ادمین {user_id} حذف شد.", show_alert=True)


# ── Add admin conversation ────────────────────────────────────────────────────

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin tapped 'Add Admin' — ask for the new admin's Telegram numeric ID."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    await query.message.reply_text(
        "➕ <b>افزودن ادمین جدید</b>\n\n"
        "لطفاً <b>آیدی عددی</b> تلگرام ادمین جدید را وارد کنید.\n\n"
        "💡 برای یافتن آیدی عددی، از ربات <b>@UserInfoBot</b> استفاده کنید:\n"
        "کافیست پیامی به آن ربات بفرستید و آیدی عددی خود را دریافت کنید.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return AA_ID


async def aa_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive numeric admin ID, ask for display name."""
    text = update.message.text.strip()
    if text == "❌ انصراف":
        await update.message.reply_text(
            "❌ عملیات لغو شد.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return ConversationHandler.END
    if not text.isdigit():
        await update.message.reply_text(
            "❌ آیدی باید فقط عدد باشد. لطفاً دوباره وارد کنید:",
            reply_markup=cancel_keyboard(),
        )
        return AA_ID
    context.user_data[_CTX_NEW_ADMIN_ID] = int(text)
    await update.message.reply_text(
        f"✅ آیدی <code>{text}</code> دریافت شد.\n\n"
        "حالا یک <b>نام نمایشی</b> برای این ادمین وارد کنید:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return AA_NAME


async def aa_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the new admin to DB and update the in-memory cache."""
    name = update.message.text.strip()
    if name == "❌ انصراف":
        await update.message.reply_text(
            "❌ عملیات لغو شد.",
            reply_markup=admin_main_menu_keyboard(),
        )
        context.user_data.pop(_CTX_NEW_ADMIN_ID, None)
        return ConversationHandler.END
    if not name:
        await update.message.reply_text("❌ نام نمی‌تواند خالی باشد. دوباره وارد کنید:")
        return AA_NAME
    user_id = context.user_data.pop(_CTX_NEW_ADMIN_ID, None)
    if user_id is None:
        await update.message.reply_text("❌ خطا در نشست. لطفاً دوباره امتحان کنید.")
        return ConversationHandler.END
    await db.add_admin(user_id, name)
    # Update in-memory cache immediately
    _db_admin_ids.add(user_id)
    await update.message.reply_text(
        f"✅ ادمین <b>{html.escape(name)}</b> (آیدی: <code>{user_id}</code>) با موفقیت اضافه شد.",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ── Premium emoji configuration ───────────────────────────────────────────────

async def settings_emoji_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the premium emoji slot management panel."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    slots_data = []
    for slot, fallback in SLOTS.items():
        val = await db.get_setting(slot)
        slots_data.append((slot, SLOT_LABELS[slot], bool(val)))
    await query.message.reply_text(
        "🌟 <b>ایموجی‌های پریمیوم</b>\n\n"
        "ایموجی‌های پریمیوم برای کاربران دارای اشتراک به‌صورت متحرک و "
        "برای سایر کاربران به‌صورت معمولی نمایش داده می‌شوند.\n\n"
        "🟢 تنظیم شده  |  ⚪ تنظیم نشده",
        parse_mode="HTML",
        reply_markup=emoji_slots_keyboard(slots_data),
    )


async def se_slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin tapped 'Set' for a specific emoji slot — ask for the custom emoji."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    slot = query.data.replace("admin_emoji_set_", "")
    label = SLOT_LABELS.get(slot, slot)
    fallback = SLOTS.get(slot, "⭐")
    context.user_data[_CTX_EMOJI_SLOT] = slot
    await query.message.reply_text(
        f"🌟 <b>تنظیم ایموجی: {label}</b>\n\n"
        f"یک پیام حاوی ایموجی پریمیوم بفرستید.\n"
        f"(نمونه پیش‌فرض در صورت عدم تنظیم: {fallback})",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return SE_EMOJI


async def se_get_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Extract the custom_emoji_id from admin's message and save it."""
    if update.message.text and update.message.text.strip() == "❌ انصراف":
        context.user_data.pop(_CTX_EMOJI_SLOT, None)
        await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=admin_main_menu_keyboard())
        return ConversationHandler.END

    entities = update.message.entities or []
    custom_entity = next(
        (e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI),
        None,
    )
    if not custom_entity:
        await update.message.reply_text(
            "❌ ایموجی پریمیوم یافت نشد.\n\n"
            "لطفاً یک پیام حاوی ایموجی پریمیوم ارسال کنید:",
            reply_markup=cancel_keyboard(),
        )
        return SE_EMOJI

    slot = context.user_data.pop(_CTX_EMOJI_SLOT, None)
    if not slot:
        return ConversationHandler.END

    emoji_id = custom_entity.custom_emoji_id
    await db.set_setting(slot, emoji_id)

    label = SLOT_LABELS.get(slot, slot)
    fallback = SLOTS.get(slot, "⭐")
    await update.message.reply_text(
        f"✅ ایموجی برای <b>{label}</b> با موفقیت تنظیم شد!\n\n"
        f"نمایش: <tg-emoji emoji-id=\"{emoji_id}\">{fallback}</tg-emoji>",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


async def clear_emoji_slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear (reset) a configured emoji slot back to the default plain emoji."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    slot = query.data.replace("admin_emoji_clear_", "")
    await db.set_setting(slot, "")
    label = SLOT_LABELS.get(slot, slot)

    slots_data = []
    for s, fallback in SLOTS.items():
        val = await db.get_setting(s)
        slots_data.append((s, SLOT_LABELS[s], bool(val)))
    try:
        await query.edit_message_reply_markup(emoji_slots_keyboard(slots_data))
    except Exception:
        pass
    await query.answer(f"🗑 ایموجی {label} پاک شد.", show_alert=True)

"""
handlers/admin/products.py — Product CRUD and conversation handlers.

State machine overview:
    ADD_PRODUCT:  AP_NAME → AP_BASE_PRICE → AP_PROFIT → AP_REQ_TG → AP_REQ_EMAIL → AP_REQ_PASS → AP_REQ_COUNT → (save)
    EDIT_PRODUCT: EP_NAME → EP_BASE_PRICE → EP_PROFIT → EP_REQ_TG → EP_REQ_EMAIL → EP_REQ_PASS → EP_REQ_COUNT → (save)

All boolean steps use inline Yes/No buttons (no text input).
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    admin_main_menu_keyboard,
    products_list_keyboard,
    product_detail_keyboard,
    yes_no_keyboard,
    cancel_keyboard,
    cancel_skip_keyboard,
    back_inline_keyboard,
)
from handlers.utils import admin_filter
from handlers.admin._helpers import (
    CTX_PRODUCT,
    CTX_EDIT_PRODUCT,
    cancel_conversation,
    require_admin_callback,
)

# ── Conversation states ──────────────────────────────────────────────────────

(
    AP_NAME, AP_BASE_PRICE, AP_PROFIT,
    AP_REQ_TG, AP_REQ_EMAIL, AP_REQ_PASS, AP_REQ_COUNT,
) = range(7)

(
    EP_NAME, EP_BASE_PRICE, EP_PROFIT,
    EP_REQ_TG, EP_REQ_EMAIL, EP_REQ_PASS, EP_REQ_COUNT,
) = range(50, 57)


# ── Product list & detail ────────────────────────────────────────────────────

async def manage_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the '📦 Manage Products' button."""
    if not admin_filter(update):
        return
    products = await db.get_all_products()
    text = "📦 *مدیریت محصولات*\n\nیک محصول را برای مدیریت انتخاب کنید یا محصول جدیدی اضافه کنید."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=products_list_keyboard(products),
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=products_list_keyboard(products),
        )


async def product_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show details for a single product."""
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await db.get_product(product_id)
    if not product:
        await query.edit_message_text("❌ محصول یافت نشد.")
        return

    rate = await db.get_currency_rate()
    final_price = int(product["base_currency_price"] * rate) + product["admin_profit"]
    status = "✅ فعال" if product["is_active"] else "❌ غیرفعال"
    flags = []
    if product["requires_telegram_id"]:
        flags.append("📱 آیدی تلگرام")
    if product["requires_email"]:
        flags.append("📧 ایمیل")
    if product["requires_password"]:
        flags.append("🔑 رمز عبور")
    if product.get("requires_count"):
        flags.append("🔢 تعداد/مقدار")
    flags_text = ", ".join(flags) if flags else "هیچ‌کدام"

    text = (
        f"📦 *{product['name']}*\n\n"
        f"💰 قیمت پایه: {product['base_currency_price']} (ارز خارجی)\n"
        f"📈 سود مدیریت: {product['admin_profit']:,} تومان\n"
        f"💵 قیمت نهایی: {final_price:,} تومان\n"
        f"📝 موارد مورد نیاز: {flags_text}\n"
        f"📊 وضعیت: {status}"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=product_detail_keyboard(
            product_id,
            bool(product["is_active"]),
        ),
    )


async def product_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    new_status = await db.toggle_product_status(product_id)
    status_text = "فعال شد ✅" if new_status else "غیرفعال شد ❌"
    await query.edit_message_text(
        f"محصول با موفقیت {status_text}.",
        reply_markup=back_inline_keyboard("admin_product_list"),
    )


async def product_delete_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    context.user_data["pending_delete_product"] = product_id
    await query.edit_message_text(
        "⚠️ آیا از *حذف دائمی* این محصول اطمینان دارید؟",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard(
            yes_data=f"admin_product_delete_confirm_{product_id}",
            no_data="admin_product_list",
        ),
    )


async def product_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await require_admin_callback(update):
        return
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    await db.delete_product(product_id)
    await query.edit_message_text(
        "🗑 محصول حذف شد.",
        reply_markup=back_inline_keyboard("admin_product_list"),
    )


# ── Add product conversation ─────────────────────────────────────────────────

async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_PRODUCT] = {}
    await query.message.reply_text(
        "➕ *افزودن محصول جدید*\n\nمرحله ۱/۷: *نام* محصول را وارد کنید:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_NAME


async def ap_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)
    context.user_data[CTX_PRODUCT]["name"] = update.message.text.strip()
    await update.message.reply_text(
        "مرحله ۲/۷: *قیمت پایه* را به ارز خارجی وارد کنید (مثلاً 1.99):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_BASE_PRICE


async def ap_get_base_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)
    try:
        price = float(update.message.text.strip())
        if price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ مقدار نامعتبر است. لطفاً یک عدد مثبت وارد کنید:")
        return AP_BASE_PRICE
    context.user_data[CTX_PRODUCT]["base_currency_price"] = price
    await update.message.reply_text(
        "مرحله ۳/۷: *سود مدیریت* را به تومان وارد کنید (مثلاً 50000):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_PROFIT


async def ap_get_profit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)
    try:
        profit = int(update.message.text.strip())
        if profit < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ مقدار نامعتبر است. لطفاً یک عدد صحیح وارد کنید:")
        return AP_PROFIT
    context.user_data[CTX_PRODUCT]["admin_profit"] = profit
    await update.message.reply_text(
        "مرحله ۴/۷: آیا این محصول به *آیدی تلگرام خریدار* نیاز دارد؟",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ap_req_tg_yes", "ap_req_tg_no"),
    )
    return AP_REQ_TG


async def ap_req_tg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_PRODUCT]["requires_telegram_id"] = query.data == "ap_req_tg_yes"
    await query.edit_message_text(
        "مرحله ۵/۷: آیا این محصول به *ایمیل خریدار* نیاز دارد؟",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ap_req_email_yes", "ap_req_email_no"),
    )
    return AP_REQ_EMAIL


async def ap_req_email_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_PRODUCT]["requires_email"] = query.data == "ap_req_email_yes"
    await query.edit_message_text(
        "مرحله ۶/۷: آیا این محصول به *رمز عبور* نیاز دارد؟",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ap_req_pass_yes", "ap_req_pass_no"),
    )
    return AP_REQ_PASS


async def ap_req_pass_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_PRODUCT]["requires_password"] = query.data == "ap_req_pass_yes"
    await query.edit_message_text(
        "مرحله ۷/۷: آیا این محصول *تعداد/مقدار* نیاز دارد؟\n"
        "_(مثلاً ستاره تلگرام یا سکه بازی — خریدار تعداد وارد می‌کند و قیمت خودکار محاسبه می‌شود)_",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ap_req_count_yes", "ap_req_count_no"),
    )
    return AP_REQ_COUNT


async def ap_req_count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_PRODUCT]["requires_count"] = query.data == "ap_req_count_yes"

    data = context.user_data[CTX_PRODUCT]
    product_id = await db.add_product(
        name=data["name"],
        base_currency_price=data["base_currency_price"],
        admin_profit=data["admin_profit"],
        requires_telegram_id=data["requires_telegram_id"],
        requires_email=data["requires_email"],
        requires_password=data["requires_password"],
        requires_count=data["requires_count"],
    )
    context.user_data.pop(CTX_PRODUCT, None)
    await query.edit_message_text(
        f"✅ محصول *{data['name']}* با موفقیت اضافه شد (شناسه: {product_id}).",
        parse_mode="Markdown",
    )
    await query.message.reply_text("بازگشت به منو", reply_markup=admin_main_menu_keyboard())
    return ConversationHandler.END


# ── Edit product conversation ─────────────────────────────────────────────────

async def edit_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await db.get_product(product_id)
    if not product:
        await query.edit_message_text("❌ محصول یافت نشد.")
        return ConversationHandler.END
    context.user_data[CTX_EDIT_PRODUCT] = {"product_id": product_id}
    await query.message.reply_text(
        f"✏️ *ویرایش محصول: {product['name']}*\n\n"
        f"مرحله ۱/۷: *نام* جدید را وارد کنید، یا «رد کردن» را بزنید تا بدون تغییر بماند:\n"
        f"فعلی: `{product['name']}`",
        parse_mode="Markdown",
        reply_markup=cancel_skip_keyboard(),
    )
    return EP_NAME


async def ep_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)
    if update.message.text.strip() != "⏭ رد کردن":
        context.user_data[CTX_EDIT_PRODUCT]["name"] = update.message.text.strip()
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    await update.message.reply_text(
        f"مرحله ۲/۷: *قیمت پایه* جدید را وارد کنید، یا «رد کردن» را بزنید تا بدون تغییر بماند:\n"
        f"فعلی: `{product['base_currency_price']}`",
        parse_mode="Markdown",
        reply_markup=cancel_skip_keyboard(),
    )
    return EP_BASE_PRICE


async def ep_get_base_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)
    if update.message.text.strip() != "⏭ رد کردن":
        try:
            price = float(update.message.text.strip())
            if price < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ مقدار نامعتبر است. لطفاً یک عدد مثبت وارد کنید یا «رد کردن» را بزنید:")
            return EP_BASE_PRICE
        context.user_data[CTX_EDIT_PRODUCT]["base_currency_price"] = price
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    await update.message.reply_text(
        f"مرحله ۳/۷: *سود مدیریت* جدید را وارد کنید، یا «رد کردن» را بزنید تا بدون تغییر بماند:\n"
        f"فعلی: `{product['admin_profit']}`",
        parse_mode="Markdown",
        reply_markup=cancel_skip_keyboard(),
    )
    return EP_PROFIT


async def ep_get_profit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)
    if update.message.text.strip() != "⏭ رد کردن":
        try:
            profit = int(update.message.text.strip())
            if profit < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ مقدار نامعتبر است. یک عدد صحیح وارد کنید یا «رد کردن» را بزنید:")
            return EP_PROFIT
        context.user_data[CTX_EDIT_PRODUCT]["admin_profit"] = profit
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    current = "✅ بله" if product["requires_telegram_id"] else "❌ خیر"
    await update.message.reply_text(
        f"مرحله ۴/۷: آیا این محصول به *آیدی تلگرام خریدار* نیاز دارد؟\nفعلی: {current}",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ep_req_tg_yes", "ep_req_tg_no"),
    )
    return EP_REQ_TG


async def ep_req_tg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_EDIT_PRODUCT]["requires_telegram_id"] = query.data == "ep_req_tg_yes"
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    current = "✅ بله" if product["requires_email"] else "❌ خیر"
    await query.edit_message_text(
        f"مرحله ۵/۷: آیا این محصول به *ایمیل خریدار* نیاز دارد؟\nفعلی: {current}",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ep_req_email_yes", "ep_req_email_no"),
    )
    return EP_REQ_EMAIL


async def ep_req_email_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_EDIT_PRODUCT]["requires_email"] = query.data == "ep_req_email_yes"
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    current = "✅ بله" if product["requires_password"] else "❌ خیر"
    await query.edit_message_text(
        f"مرحله ۶/۷: آیا این محصول به *رمز عبور* نیاز دارد؟\nفعلی: {current}",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ep_req_pass_yes", "ep_req_pass_no"),
    )
    return EP_REQ_PASS


async def ep_req_pass_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_EDIT_PRODUCT]["requires_password"] = query.data == "ep_req_pass_yes"
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    current = "✅ بله" if product.get("requires_count") else "❌ خیر"
    await query.edit_message_text(
        f"مرحله ۷/۷: آیا این محصول *تعداد/مقدار* نیاز دارد؟\nفعلی: {current}\n"
        "_(مثلاً ستاره تلگرام — خریدار تعداد وارد می‌کند)_",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ep_req_count_yes", "ep_req_count_no"),
    )
    return EP_REQ_COUNT


async def ep_req_count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not await require_admin_callback(update):
        return ConversationHandler.END
    await query.answer()
    context.user_data[CTX_EDIT_PRODUCT]["requires_count"] = query.data == "ep_req_count_yes"
    data = context.user_data[CTX_EDIT_PRODUCT]
    product_id = data.pop("product_id")
    await db.update_product(
        product_id=product_id,
        name=data.get("name"),
        base_currency_price=data.get("base_currency_price"),
        admin_profit=data.get("admin_profit"),
        requires_telegram_id=data.get("requires_telegram_id"),
        requires_email=data.get("requires_email"),
        requires_password=data.get("requires_password"),
        requires_count=data.get("requires_count"),
    )
    context.user_data.pop(CTX_EDIT_PRODUCT, None)
    await query.edit_message_text(
        "✅ محصول با موفقیت ویرایش شد.",
        reply_markup=back_inline_keyboard("admin_product_list"),
    )
    return ConversationHandler.END

"""
handlers/admin/products.py — Product CRUD and conversation handlers.

State machine overview:
    ADD_PRODUCT:  AP_NAME → AP_BASE_PRICE → AP_PROFIT → AP_REQ_TG → AP_REQ_EMAIL → AP_REQ_PASS → (save)
    EDIT_PRODUCT: EP_NAME → EP_BASE_PRICE → EP_PROFIT → EP_REQ_TG → EP_REQ_EMAIL → EP_REQ_PASS → (save)
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import (
    admin_main_menu_keyboard,
    products_list_keyboard,
    product_detail_keyboard,
    confirm_keyboard,
    yes_no_keyboard,
    cancel_keyboard,
    back_inline_keyboard,
)
from handlers.utils import admin_filter
from handlers.admin._helpers import CTX_PRODUCT, CTX_EDIT_PRODUCT, cancel_conversation

# ── Conversation states ──────────────────────────────────────────────────────

(
    AP_NAME, AP_BASE_PRICE, AP_PROFIT,
    AP_REQ_TG, AP_REQ_EMAIL, AP_REQ_PASS,
) = range(6)

(
    EP_NAME, EP_BASE_PRICE, EP_PROFIT,
    EP_REQ_TG, EP_REQ_EMAIL, EP_REQ_PASS,
) = range(50, 56)


# ── Product list & detail ────────────────────────────────────────────────────

async def manage_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the '📦 Manage Products' button."""
    if not admin_filter(update):
        return
    products = await db.get_all_products()
    text = "📦 *Product Management*\n\nSelect a product to manage, or add a new one."
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
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await db.get_product(product_id)
    if not product:
        await query.edit_message_text("Product not found.")
        return

    rate = await db.get_currency_rate()
    final_price = int(product["base_currency_price"] * rate) + product["admin_profit"]
    status = "✅ Active" if product["is_active"] else "❌ Inactive"
    flags = []
    if product["requires_telegram_id"]:
        flags.append("Telegram ID")
    if product["requires_email"]:
        flags.append("Email")
    if product["requires_password"]:
        flags.append("Password")
    flags_text = ", ".join(flags) if flags else "None"

    text = (
        f"📦 *{product['name']}*\n\n"
        f"Base Price: {product['base_currency_price']} (foreign)\n"
        f"Admin Profit: {product['admin_profit']:,} T\n"
        f"Final Price: {final_price:,} T\n"
        f"Requires: {flags_text}\n"
        f"Status: {status}"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=product_detail_keyboard(product_id, bool(product["is_active"])),
    )


async def product_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    new_status = await db.toggle_product_status(product_id)
    status_text = "activated ✅" if new_status else "deactivated ❌"
    await query.edit_message_text(
        f"Product has been {status_text}.",
        reply_markup=back_inline_keyboard("admin_product_list"),
    )


async def product_delete_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    context.user_data["pending_delete_product"] = product_id
    await query.edit_message_text(
        "⚠️ Are you sure you want to *permanently delete* this product?",
        parse_mode="Markdown",
        reply_markup=confirm_keyboard(
            yes_data=f"admin_product_delete_confirm_{product_id}",
            no_data="admin_product_list",
        ),
    )


async def product_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    await db.delete_product(product_id)
    await query.edit_message_text(
        "🗑 Product deleted.",
        reply_markup=back_inline_keyboard("admin_product_list"),
    )


# ── Add product conversation ─────────────────────────────────────────────────

async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data[CTX_PRODUCT] = {}
    await query.message.reply_text(
        "➕ *Add New Product*\n\nStep 1/6: Enter the product *name*:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_NAME


async def ap_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    context.user_data[CTX_PRODUCT]["name"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 2/6: Enter the *base price* in foreign currency (e.g. 1.99):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_BASE_PRICE


async def ap_get_base_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    try:
        price = float(update.message.text.strip())
        if price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid number. Please enter a positive number:")
        return AP_BASE_PRICE
    context.user_data[CTX_PRODUCT]["base_currency_price"] = price
    await update.message.reply_text(
        "Step 3/6: Enter the *admin profit* in Toman (integer, e.g. 50000):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_PROFIT


async def ap_get_profit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    try:
        profit = int(update.message.text.strip())
        if profit < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid integer. Please enter a non-negative integer:")
        return AP_PROFIT
    context.user_data[CTX_PRODUCT]["admin_profit"] = profit
    await update.message.reply_text(
        "Step 4/6: Does this product *require the buyer's Telegram ID*? (yes / no)",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_REQ_TG


async def ap_get_req_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    answer = update.message.text.strip().lower()
    if answer not in ("yes", "no"):
        await update.message.reply_text("Please reply with *yes* or *no*:", parse_mode="Markdown")
        return AP_REQ_TG
    context.user_data[CTX_PRODUCT]["requires_telegram_id"] = answer == "yes"
    await update.message.reply_text(
        "Step 5/6: Does this product *require the buyer's Email*? (yes / no)",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_REQ_EMAIL


async def ap_get_req_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    answer = update.message.text.strip().lower()
    if answer not in ("yes", "no"):
        await update.message.reply_text("Please reply with *yes* or *no*:", parse_mode="Markdown")
        return AP_REQ_EMAIL
    context.user_data[CTX_PRODUCT]["requires_email"] = answer == "yes"
    await update.message.reply_text(
        "Step 6/6: Does this product *require a Password*? (yes / no)",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_REQ_PASS


async def ap_get_req_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    answer = update.message.text.strip().lower()
    if answer not in ("yes", "no"):
        await update.message.reply_text("Please reply with *yes* or *no*:", parse_mode="Markdown")
        return AP_REQ_PASS
    context.user_data[CTX_PRODUCT]["requires_password"] = answer == "yes"

    data = context.user_data[CTX_PRODUCT]
    product_id = await db.add_product(
        name=data["name"],
        base_currency_price=data["base_currency_price"],
        admin_profit=data["admin_profit"],
        requires_telegram_id=data["requires_telegram_id"],
        requires_email=data["requires_email"],
        requires_password=data["requires_password"],
    )
    context.user_data.pop(CTX_PRODUCT, None)
    await update.message.reply_text(
        f"✅ Product *{data['name']}* added successfully (ID: {product_id}).",
        parse_mode="Markdown",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ── Edit product conversation ─────────────────────────────────────────────────

async def edit_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await db.get_product(product_id)
    if not product:
        await query.edit_message_text("Product not found.")
        return ConversationHandler.END
    context.user_data[CTX_EDIT_PRODUCT] = {"product_id": product_id}
    await query.message.reply_text(
        f"✏️ *Edit Product: {product['name']}*\n\n"
        f"Step 1/6: Enter a new *name*, or send /skip to keep current:\n"
        f"Current: `{product['name']}`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return EP_NAME


async def ep_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    if update.message.text.strip() != "/skip":
        context.user_data[CTX_EDIT_PRODUCT]["name"] = update.message.text.strip()
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    await update.message.reply_text(
        f"Step 2/6: Enter a new *base price* in foreign currency, or /skip to keep current:\n"
        f"Current: `{product['base_currency_price']}`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return EP_BASE_PRICE


async def ep_get_base_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    if update.message.text.strip() != "/skip":
        try:
            price = float(update.message.text.strip())
            if price < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Please enter a positive number or /skip:")
            return EP_BASE_PRICE
        context.user_data[CTX_EDIT_PRODUCT]["base_currency_price"] = price
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    await update.message.reply_text(
        f"Step 3/6: Enter a new *admin profit* in Toman, or /skip to keep current:\n"
        f"Current: `{product['admin_profit']}`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return EP_PROFIT


async def ep_get_profit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await cancel_conversation(update, context)
    if update.message.text.strip() != "/skip":
        try:
            profit = int(update.message.text.strip())
            if profit < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Invalid integer. Enter a non-negative integer or /skip:")
            return EP_PROFIT
        context.user_data[CTX_EDIT_PRODUCT]["admin_profit"] = profit
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    current = "✅ Yes" if product["requires_telegram_id"] else "❌ No"
    await update.message.reply_text(
        f"Step 4/6: Should this product *require the buyer's Telegram ID*?\nCurrent: {current}",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ep_req_tg_yes", "ep_req_tg_no"),
    )
    return EP_REQ_TG


async def ep_req_tg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data[CTX_EDIT_PRODUCT]["requires_telegram_id"] = query.data == "ep_req_tg_yes"
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    current = "✅ Yes" if product["requires_email"] else "❌ No"
    await query.edit_message_text(
        f"Step 5/6: Should this product *require the buyer's Email*?\nCurrent: {current}",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ep_req_email_yes", "ep_req_email_no"),
    )
    return EP_REQ_EMAIL


async def ep_req_email_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data[CTX_EDIT_PRODUCT]["requires_email"] = query.data == "ep_req_email_yes"
    product_id = context.user_data[CTX_EDIT_PRODUCT]["product_id"]
    product = await db.get_product(product_id)
    current = "✅ Yes" if product["requires_password"] else "❌ No"
    await query.edit_message_text(
        f"Step 6/6: Should this product *require a Password*?\nCurrent: {current}",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard("ep_req_pass_yes", "ep_req_pass_no"),
    )
    return EP_REQ_PASS


async def ep_req_pass_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data[CTX_EDIT_PRODUCT]["requires_password"] = query.data == "ep_req_pass_yes"
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
    )
    context.user_data.pop(CTX_EDIT_PRODUCT, None)
    await query.edit_message_text(
        "✅ Product updated successfully.",
        reply_markup=back_inline_keyboard("admin_product_list"),
    )
    return ConversationHandler.END

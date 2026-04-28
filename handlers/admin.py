"""
handlers/admin.py — All admin panel ConversationHandlers and callback query handlers.

State machine overview
──────────────────────
ADD_PRODUCT conversation:
    AP_NAME → AP_BASE_PRICE → AP_PROFIT → AP_REQ_TG → AP_REQ_EMAIL → AP_REQ_PASS → (save)

EDIT_PRODUCT conversation:
    EP_NAME → EP_BASE_PRICE → EP_PROFIT → EP_REQ_TG → EP_REQ_EMAIL → EP_REQ_PASS → (save)

ADD_CARD conversation:
    AC_NUMBER → AC_HOLDER → (save)

SET_RATE conversation (manual branch only):
    SR_VALUE → (save)

ADD_DISCOUNT conversation:
    AD_CODE → AD_PERCENT → (save)

BROADCAST conversation:
    BC_MESSAGE → (send to all)
"""

import math
import os
import logging
from typing import Optional

import httpx
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

import database as db
from keyboards import (
    admin_main_menu_keyboard,
    products_list_keyboard,
    product_detail_keyboard,
    confirm_keyboard,
    yes_no_keyboard,
    cards_list_keyboard,
    card_detail_keyboard,
    discounts_list_keyboard,
    discount_detail_keyboard,
    currency_rate_mode_keyboard,
    transaction_review_keyboard,
    order_review_keyboard,
    order_payment_review_keyboard,
    cancel_keyboard,
    back_inline_keyboard,
    main_menu_keyboard,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_admin_ids() -> list[int]:
    raw = os.getenv("ADMIN_IDS", "")
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


def is_admin(user_id: int) -> bool:
    return user_id in _get_admin_ids()


def _admin_filter(update: Update) -> bool:
    user = update.effective_user
    return user is not None and is_admin(user.id)


# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------

(
    AP_NAME, AP_BASE_PRICE, AP_PROFIT,
    AP_REQ_TG, AP_REQ_EMAIL, AP_REQ_PASS,
) = range(6)

# Edit product states (separate integer range)
(
    EP_NAME, EP_BASE_PRICE, EP_PROFIT,
    EP_REQ_TG, EP_REQ_EMAIL, EP_REQ_PASS,
) = range(50, 56)

AC_NUMBER = 10
AC_HOLDER = 11

SR_VALUE = 20

AD_CODE, AD_PERCENT = 30, 31

BC_MESSAGE = 40

# Context keys used to carry partial data through conversations
_CTX_PRODUCT = "new_product"
_CTX_EDIT_PRODUCT = "edit_product"
_CTX_DISCOUNT = "new_discount"
_CTX_CARD = "new_card"


# ---------------------------------------------------------------------------
# Admin entry point
# ---------------------------------------------------------------------------

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point: /admin command — only visible to admins."""
    if not _admin_filter(update):
        await update.message.reply_text("⛔ Access denied.")
        return
    await db.ensure_user(update.effective_user.id)
    await update.message.reply_text(
        "👑 Welcome to the Admin Panel.",
        reply_markup=admin_main_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# Helper: send the admin main menu via edit or new message
# ---------------------------------------------------------------------------

async def _go_admin_main(update: Update) -> None:
    text = "👑 Admin Panel — choose an option:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text)
        # ReplyKeyboard can't be set via edit; just leave it
    else:
        await update.message.reply_text(text, reply_markup=admin_main_menu_keyboard())


# ---------------------------------------------------------------------------
# Generic back-to-main callback
# ---------------------------------------------------------------------------

async def admin_back_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "👑 Admin Panel — choose an option:",
        reply_markup=None,
    )


# ===========================================================================
# SECTION 1: Product management
# ===========================================================================

async def manage_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the '📦 Manage Products' button."""
    if not _admin_filter(update):
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


# --- Add product conversation ---

async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data[_CTX_PRODUCT] = {}
    await query.message.reply_text(
        "➕ *Add New Product*\n\nStep 1/6: Enter the product *name*:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_NAME


async def ap_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    context.user_data[_CTX_PRODUCT]["name"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 2/6: Enter the *base price* in foreign currency (e.g. 1.99):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_BASE_PRICE


async def ap_get_base_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    try:
        price = float(update.message.text.strip())
        if price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid number. Please enter a positive number:")
        return AP_BASE_PRICE
    context.user_data[_CTX_PRODUCT]["base_currency_price"] = price
    await update.message.reply_text(
        "Step 3/6: Enter the *admin profit* in Toman (integer, e.g. 50000):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_PROFIT


async def ap_get_profit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    try:
        profit = int(update.message.text.strip())
        if profit < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid integer. Please enter a non-negative integer:")
        return AP_PROFIT
    context.user_data[_CTX_PRODUCT]["admin_profit"] = profit
    await update.message.reply_text(
        "Step 4/6: Does this product *require the buyer's Telegram ID*? (yes / no)",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_REQ_TG


async def ap_get_req_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    answer = update.message.text.strip().lower()
    if answer not in ("yes", "no"):
        await update.message.reply_text("Please reply with *yes* or *no*:", parse_mode="Markdown")
        return AP_REQ_TG
    context.user_data[_CTX_PRODUCT]["requires_telegram_id"] = answer == "yes"
    await update.message.reply_text(
        "Step 5/6: Does this product *require the buyer's Email*? (yes / no)",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_REQ_EMAIL


async def ap_get_req_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    answer = update.message.text.strip().lower()
    if answer not in ("yes", "no"):
        await update.message.reply_text("Please reply with *yes* or *no*:", parse_mode="Markdown")
        return AP_REQ_EMAIL
    context.user_data[_CTX_PRODUCT]["requires_email"] = answer == "yes"
    await update.message.reply_text(
        "Step 6/6: Does this product *require a Password*? (yes / no)",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AP_REQ_PASS


async def ap_get_req_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    answer = update.message.text.strip().lower()
    if answer not in ("yes", "no"):
        await update.message.reply_text("Please reply with *yes* or *no*:", parse_mode="Markdown")
        return AP_REQ_PASS
    context.user_data[_CTX_PRODUCT]["requires_password"] = answer == "yes"

    data = context.user_data[_CTX_PRODUCT]
    product_id = await db.add_product(
        name=data["name"],
        base_currency_price=data["base_currency_price"],
        admin_profit=data["admin_profit"],
        requires_telegram_id=data["requires_telegram_id"],
        requires_email=data["requires_email"],
        requires_password=data["requires_password"],
    )
    context.user_data.pop(_CTX_PRODUCT, None)
    await update.message.reply_text(
        f"✅ Product *{data['name']}* added successfully (ID: {product_id}).",
        parse_mode="Markdown",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# --- Edit product conversation ---

async def edit_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await db.get_product(product_id)
    if not product:
        await query.edit_message_text("Product not found.")
        return ConversationHandler.END
    context.user_data[_CTX_EDIT_PRODUCT] = {"product_id": product_id}
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
        return await _cancel_conversation(update, context)
    if update.message.text.strip() != "/skip":
        context.user_data[_CTX_EDIT_PRODUCT]["name"] = update.message.text.strip()
    product_id = context.user_data[_CTX_EDIT_PRODUCT]["product_id"]
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
        return await _cancel_conversation(update, context)
    if update.message.text.strip() != "/skip":
        try:
            price = float(update.message.text.strip())
            if price < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Please enter a positive number or /skip:")
            return EP_BASE_PRICE
        context.user_data[_CTX_EDIT_PRODUCT]["base_currency_price"] = price
    product_id = context.user_data[_CTX_EDIT_PRODUCT]["product_id"]
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
        return await _cancel_conversation(update, context)
    if update.message.text.strip() != "/skip":
        try:
            profit = int(update.message.text.strip())
            if profit < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Invalid integer. Enter a non-negative integer or /skip:")
            return EP_PROFIT
        context.user_data[_CTX_EDIT_PRODUCT]["admin_profit"] = profit
    product_id = context.user_data[_CTX_EDIT_PRODUCT]["product_id"]
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
    context.user_data[_CTX_EDIT_PRODUCT]["requires_telegram_id"] = query.data == "ep_req_tg_yes"
    product_id = context.user_data[_CTX_EDIT_PRODUCT]["product_id"]
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
    context.user_data[_CTX_EDIT_PRODUCT]["requires_email"] = query.data == "ep_req_email_yes"
    product_id = context.user_data[_CTX_EDIT_PRODUCT]["product_id"]
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
    context.user_data[_CTX_EDIT_PRODUCT]["requires_password"] = query.data == "ep_req_pass_yes"
    data = context.user_data[_CTX_EDIT_PRODUCT]
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
    context.user_data.pop(_CTX_EDIT_PRODUCT, None)
    await query.edit_message_text(
        "✅ Product updated successfully.",
        reply_markup=back_inline_keyboard("admin_product_list"),
    )
    return ConversationHandler.END


# ===========================================================================
# SECTION 2: Card management
# ===========================================================================

async def manage_cards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _admin_filter(update):
        return
    cards = await db.get_all_cards()
    text = "💳 *Card Management*\n\nSelect a card to manage, or add a new one."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=cards_list_keyboard(cards),
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=cards_list_keyboard(cards),
        )


async def card_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    card_id = int(query.data.split("_")[-1])
    cards = await db.get_all_cards()
    card = next((c for c in cards if c["card_id"] == card_id), None)
    if not card:
        await query.edit_message_text("Card not found.")
        return
    status = "✅ Active" if card["is_active"] else "❌ Inactive"
    holder = card.get("cardholder_name") or "N/A"
    await query.edit_message_text(
        f"💳 Card: <code>{card['card_number']}</code>\n"
        f"Cardholder: {holder}\n"
        f"Status: {status}",
        parse_mode="HTML",
        reply_markup=card_detail_keyboard(card_id, bool(card["is_active"])),
    )


async def card_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    card_id = int(query.data.split("_")[-1])
    new_status = await db.toggle_card_status(card_id)
    status_text = "activated ✅" if new_status else "deactivated ❌"
    await query.edit_message_text(
        f"Card has been {status_text}.",
        reply_markup=back_inline_keyboard("admin_card_list"),
    )


async def card_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    card_id = int(query.data.split("_")[-1])
    await db.delete_card(card_id)
    await query.edit_message_text(
        "🗑 Card deleted.",
        reply_markup=back_inline_keyboard("admin_card_list"),
    )


# --- Add card conversation ---

async def add_card_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data[_CTX_CARD] = {}
    await query.message.reply_text(
        "➕ *Add New Card*\n\nStep 1/2: Enter the *card number*:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AC_NUMBER


async def ac_get_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    card_number = update.message.text.strip()
    if not card_number:
        await update.message.reply_text("❌ Card number cannot be empty. Try again:")
        return AC_NUMBER
    context.user_data[_CTX_CARD]["card_number"] = card_number
    await update.message.reply_text(
        "Step 2/2: Enter the *cardholder name*:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AC_HOLDER


async def ac_get_holder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    holder = update.message.text.strip()
    card_number = context.user_data[_CTX_CARD]["card_number"]
    card_id = await db.add_card(card_number, holder)
    context.user_data.pop(_CTX_CARD, None)
    await update.message.reply_text(
        f"✅ Card added (ID: {card_id}):\n"
        f"<code>{card_number}</code>\n"
        f"Cardholder: {holder}",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ===========================================================================
# SECTION 3: Currency rate
# ===========================================================================

async def set_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the rate-mode selector (manual vs auto)."""
    if not _admin_filter(update):
        return
    current = await db.get_currency_rate()
    is_auto = await db.get_setting("is_auto_currency") == "1"
    mode_text = "🤖 Auto (API)" if is_auto else "✏️ Manual"
    await update.message.reply_text(
        f"💰 *Currency Rate Settings*\n\n"
        f"Current rate: *{current:,.0f} T*\n"
        f"Mode: {mode_text}\n\n"
        f"Choose an action:",
        parse_mode="Markdown",
        reply_markup=currency_rate_mode_keyboard(),
    )


async def rate_manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin chose Manual Update — start the manual-entry conversation."""
    query = update.callback_query
    await query.answer()
    await db.set_setting("is_auto_currency", "0")
    current = await db.get_currency_rate()
    await query.message.reply_text(
        f"✏️ *Manual Update*\n\nCurrent rate: *{current:,.0f} T*\n\nEnter the new rate (Toman per 1 foreign currency unit):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return SR_VALUE


async def rate_auto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin chose Auto Update — enable the flag and immediately fetch once."""
    query = update.callback_query
    await query.answer()
    await db.set_setting("is_auto_currency", "1")
    rate = await _fetch_and_save_rate()
    if rate:
        await query.edit_message_text(
            f"✅ Auto-update *enabled*.\nRate fetched from API: *{rate:,} T*\n"
            f"_(Updates every 3 hours)_",
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            "❌ Auto-update enabled, but the initial API fetch *failed*. "
            "The rate will be retried on the next scheduled run (3 h).",
            parse_mode="Markdown",
        )


async def sr_get_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    try:
        rate = float(update.message.text.strip().replace(",", ""))
        if rate < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid number. Enter a positive number:")
        return SR_VALUE
    await db.set_setting("currency_rate", str(rate))
    await update.message.reply_text(
        f"✅ Currency rate updated to *{rate:,.2f} T*.",
        parse_mode="Markdown",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


async def _fetch_and_save_rate() -> Optional[int]:
    """
    Fetch USDT/RLS mark price from Nobitex, convert Rials → Tomans,
    round UP to the nearest 1,000 T, and persist in Settings.
    Returns the saved Toman value, or None on failure.
    """
    url = "https://apiv2.nobitex.ir/market/stats?srcCurrency=usdt&dstCurrency=rls"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        mark_price_str = data["stats"]["usdt-rls"]["mark"]
        rial_price = float(mark_price_str)
        toman_price = rial_price / 10
        rounded = math.ceil(toman_price / 1000) * 1000
        await db.set_setting("currency_rate", str(rounded))
        logger.info("Auto currency rate updated: %s T", rounded)
        return rounded
    except Exception as exc:
        logger.error("Failed to fetch currency rate: %s", exc)
        return None


async def auto_rate_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback — runs every 3 hours."""
    is_auto = await db.get_setting("is_auto_currency") == "1"
    if not is_auto:
        return
    await _fetch_and_save_rate()


# ===========================================================================
# SECTION 4: Discount management
# ===========================================================================

async def manage_discounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _admin_filter(update):
        return
    discounts = await db.get_all_discounts()
    text = "🏷 *Discount Management*\n\nSelect a discount to manage, or add a new one."
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
    await query.answer()
    # callback_data = "admin_discount_<code>"
    code = "_".join(query.data.split("_")[2:])
    discount = await db.get_discount(code) or await _get_discount_any(code)
    if not discount:
        await query.edit_message_text("Discount not found.")
        return
    status = "✅ Active" if discount["is_active"] else "❌ Inactive"
    pct = discount.get("percentage_discount", discount.get("amount", 0))
    await query.edit_message_text(
        f"🏷 Code: <code>{discount['code']}</code>\nDiscount: {pct}%\nStatus: {status}",
        parse_mode="HTML",
        reply_markup=discount_detail_keyboard(code),
    )


async def _get_discount_any(code: str) -> Optional[dict]:
    """Fetch discount regardless of active status (for admin view)."""
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM Discounts WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def discount_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # callback_data = "admin_discount_delete_<code>"
    code = "_".join(query.data.split("_")[3:])
    await db.delete_discount(code)
    await query.edit_message_text(
        "🗑 Discount deleted.",
        reply_markup=back_inline_keyboard("admin_discount_list"),
    )


# --- Add discount conversation ---

async def add_discount_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data[_CTX_DISCOUNT] = {}
    await query.message.reply_text(
        "➕ *Add Discount Code*\n\nStep 1/2: Enter the discount *code* (text string):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AD_CODE


async def ad_get_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    code = update.message.text.strip()
    if not code:
        await update.message.reply_text("❌ Code cannot be empty. Try again:")
        return AD_CODE
    context.user_data[_CTX_DISCOUNT]["code"] = code
    await update.message.reply_text(
        "Step 2/2: Enter the *discount percentage* (1–100):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AD_PERCENT


async def ad_get_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    try:
        pct = int(update.message.text.strip())
        if not (1 <= pct <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Enter an integer between 1 and 100:")
        return AD_PERCENT
    code = context.user_data[_CTX_DISCOUNT]["code"]
    await db.add_discount(code, pct)
    context.user_data.pop(_CTX_DISCOUNT, None)
    await update.message.reply_text(
        f"✅ Discount code <code>{code}</code> ({pct}%) added.",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ===========================================================================
# SECTION 5: Transaction & Order review
# ===========================================================================

async def pending_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all pending wallet top-up transactions."""
    if not _admin_filter(update):
        return
    transactions = await db.get_pending_transactions()
    if not transactions:
        await update.message.reply_text(
            "✅ No pending transactions.", reply_markup=admin_main_menu_keyboard()
        )
        return
    for tx in transactions:
        text = (
            f"💳 *Transaction #{tx['transaction_id']}*\n"
            f"User: `{tx['user_id']}`\n"
            f"Amount: {tx['amount']:,} T\n"
            f"Date: {tx['created_at']}"
        )
        if tx["receipt_photo_id"]:
            await update.message.reply_photo(
                photo=tx["receipt_photo_id"],
                caption=text,
                parse_mode="Markdown",
                reply_markup=transaction_review_keyboard(tx["transaction_id"]),
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=transaction_review_keyboard(tx["transaction_id"]),
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


async def processing_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all orders that are in PROCESSING state (paid, awaiting manual fulfillment)."""
    if not _admin_filter(update):
        return
    orders = await db.get_orders_by_status("PROCESSING")
    if not orders:
        await update.message.reply_text(
            "✅ No orders in PROCESSING state.", reply_markup=admin_main_menu_keyboard()
        )
        return
    for order in orders:
        details = []
        if order.get("input_telegram_id"):
            details.append(f"Telegram ID: `{order['input_telegram_id']}`")
        if order.get("input_email"):
            details.append(f"Email: `{order['input_email']}`")
        if order.get("input_password"):
            details.append(f"Password: `{order['input_password']}`")
        details_text = "\n".join(details) if details else "No extra details."
        text = (
            f"📋 *Order #{order['order_id']}*\n"
            f"Product: {order['product_name']}\n"
            f"User: `{order['user_id']}`\n"
            f"Paid: {order['final_price_paid']:,} T\n"
            f"Method: {order['payment_method']}\n"
            f"Date: {order['created_at']}\n\n"
            f"{details_text}"
        )
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
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
    await query.edit_message_text(f"✅ Payment for Order #{order_id} approved. Status → PROCESSING.")
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"✅ Your payment for order #{order_id} has been verified. We are now processing your order!",
        )
    except Exception:
        logger.warning("Could not notify user %s about approved order.", order["user_id"])


# ===========================================================================
# SECTION 6: Broadcast
# ===========================================================================

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _admin_filter(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📣 *Broadcast*\n\nSend the message you want to broadcast to all users.\n_(HTML supported)_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return BC_MESSAGE


async def bc_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Cancel":
        return await _cancel_conversation(update, context)
    message_text = update.message.text
    users = await db.get_all_users()
    sent, failed = 0, 0
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["user_id"], text=message_text, parse_mode="HTML"
            )
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"📣 Broadcast complete.\n✅ Sent: {sent}\n❌ Failed: {failed}",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ===========================================================================
# Shared cancel helper
# ===========================================================================

async def _cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop(_CTX_PRODUCT, None)
    context.user_data.pop(_CTX_EDIT_PRODUCT, None)
    context.user_data.pop(_CTX_DISCOUNT, None)
    context.user_data.pop(_CTX_CARD, None)
    await update.message.reply_text(
        "❌ Operation cancelled.",
        reply_markup=admin_main_menu_keyboard(),
    )
    return ConversationHandler.END


# ===========================================================================
# ConversationHandler builders (imported in bot.py)
# ===========================================================================

def build_add_product_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(add_product_start, pattern="^admin_product_add$")],
        states={
            AP_NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_name)],
            AP_BASE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_base_price)],
            AP_PROFIT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_profit)],
            AP_REQ_TG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_req_tg)],
            AP_REQ_EMAIL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_req_email)],
            AP_REQ_PASS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_req_pass)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel$"), _cancel_conversation)],
        allow_reentry=True,
    )


def build_add_card_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(add_card_start, pattern="^admin_card_add$")],
        states={
            AC_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ac_get_number)],
            AC_HOLDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ac_get_holder)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel$"), _cancel_conversation)],
        allow_reentry=True,
    )


def build_set_rate_conv() -> ConversationHandler:
    """Manual-entry branch of the rate conversation (auto branch uses callbacks only)."""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(rate_manual_callback, pattern="^admin_rate_manual$")],
        states={
            SR_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sr_get_value)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel$"), _cancel_conversation)],
        allow_reentry=True,
    )


def build_add_discount_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(add_discount_start, pattern="^admin_discount_add$")],
        states={
            AD_CODE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_code)],
            AD_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_percent)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel$"), _cancel_conversation)],
        allow_reentry=True,
    )


def build_edit_product_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_product_start, pattern=r"^admin_product_edit_\d+$")],
        states={
            EP_NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, ep_get_name)],
            EP_BASE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ep_get_base_price)],
            EP_PROFIT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ep_get_profit)],
            EP_REQ_TG:     [CallbackQueryHandler(ep_req_tg_callback, pattern="^ep_req_tg_(yes|no)$")],
            EP_REQ_EMAIL:  [CallbackQueryHandler(ep_req_email_callback, pattern="^ep_req_email_(yes|no)$")],
            EP_REQ_PASS:   [CallbackQueryHandler(ep_req_pass_callback, pattern="^ep_req_pass_(yes|no)$")],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel$"), _cancel_conversation)],
        allow_reentry=True,
    )


def build_broadcast_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📣 Broadcast$"), broadcast_start)],
        states={
            BC_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bc_send)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel$"), _cancel_conversation)],
        allow_reentry=True,
    )

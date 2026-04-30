"""
handlers/shop/_helpers.py — Shared helpers, context keys, and state constants for the shop package.
"""

import html
import random

from telegram.ext import ContextTypes

import database as db
from keyboards import checkout_keyboard

# ── Context keys ─────────────────────────────────────────────────────────────

CTX_ORDER = "shop_order"
CTX_TOPUP = "shop_topup"

# ── Conversation states ─────────────────────────────────────────────────────

(
    COLLECT_TG_ID,
    COLLECT_EMAIL,
    COLLECT_PASSWORD,
    COLLECT_DISCOUNT,
    COLLECT_RECEIPT,
    CHECKOUT,
) = range(100, 106)

(
    TOPUP_AMOUNT,
    TOPUP_RECEIPT,
) = range(110, 112)


# ── Invoice helpers ──────────────────────────────────────────────────────────

def build_invoice_text(order: dict) -> str:
    """Format the order summary text."""
    lines = ["🧾 <b>Order Summary</b>\n"]
    lines.append(f"📦 Product: <b>{html.escape(order['product_name'])}</b>")
    lines.append(f"💰 Price: <b>{order['final_price']:,} Tomans</b>")
    if order.get("discount_pct"):
        lines.append(f"🏷 Discount: <b>{order['discount_pct']}%</b> applied")
    if order.get("input_telegram_id"):
        lines.append(f"📱 Telegram: <code>{html.escape(order['input_telegram_id'])}</code>")
    if order.get("input_email"):
        lines.append(f"📧 Email: <code>{html.escape(order['input_email'])}</code>")
    if order.get("input_password"):
        lines.append("🔑 Password: ✅ Provided")
    return "\n".join(lines)


async def show_invoice(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render the invoice and end the input-collection sub-flow."""
    order = context.user_data[CTX_ORDER]
    user = await db.get_user(message.chat.id)
    wallet = user["wallet_balance"] if user else 0
    await message.reply_text(
        build_invoice_text(order),
        parse_mode="HTML",
        reply_markup=checkout_keyboard(wallet),
    )
    return CHECKOUT


async def advance(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Move to the next required input step, or show the invoice when all
    required inputs have been collected.
    """
    order = context.user_data[CTX_ORDER]

    if order["requires_telegram_id"] and order["input_telegram_id"] is None:
        await message.reply_text(
            "📱 Please send your <b>Telegram username</b>\n"
            "(e.g. <code>@mahdirnj</code> or just <code>mahdirnj</code>).\n\n"
            "<i>Send /cancel at any time to abort.</i>",
            parse_mode="HTML",
        )
        return COLLECT_TG_ID

    if order["requires_email"] and order["input_email"] is None:
        await message.reply_text(
            "📧 Please send your <b>Email address</b>.\n\n"
            "<i>Send /cancel at any time to abort.</i>",
            parse_mode="HTML",
        )
        return COLLECT_EMAIL

    if order["requires_password"] and order["input_password"] is None:
        await message.reply_text(
            "🔑 Please send the <b>Password</b> for your account.\n\n"
            "<i>Send /cancel at any time to abort.</i>",
            parse_mode="HTML",
        )
        return COLLECT_PASSWORD

    return await show_invoice(message, context)


async def send_card_and_ask_receipt(message, context, amount: int):
    """Pick a random active card and ask user to send a receipt photo."""
    cards = await db.get_all_cards(active_only=True)
    if not cards:
        await message.reply_text(
            "❌ No active payment cards are configured right now. "
            "Please try again later or contact support."
        )
        return False
    card = random.choice(cards)
    holder = html.escape(card.get("cardholder_name") or "")
    holder_line = f"\n👤 Cardholder: <b>{holder}</b>" if holder else ""
    await message.reply_text(
        f"💳 Please transfer <b>{amount:,} Tomans</b> to:\n\n"
        f"<code>{html.escape(card['card_number'])}</code>{holder_line}\n\n"
        "After transferring, send a <b>photo of the receipt</b> here.",
        parse_mode="HTML",
    )
    return True

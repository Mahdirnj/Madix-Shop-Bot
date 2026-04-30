"""
handlers/shop/browsing.py — Shop menu and product detail browsing.
"""

import html

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import database as db
from keyboards import shop_products_keyboard, product_buy_keyboard


async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await db.ensure_user(update.effective_user.id)
    products = await db.get_all_products(active_only=True)
    if not products:
        await update.message.reply_text("🏪 The shop is currently empty. Check back later!")
        return
    await update.message.reply_text(
        "🛍 <b>Shop</b>\n\nSelect a product to view its details:",
        parse_mode="HTML",
        reply_markup=shop_products_keyboard(products),
    )


async def shop_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await db.get_product(product_id)
    if not product or not product["is_active"]:
        try:
            await query.edit_message_text("❌ This product is no longer available.")
        except BadRequest:
            pass
        return
    rate = await db.get_currency_rate()
    final_price = int(product["base_currency_price"] * rate) + product["admin_profit"]
    flags = []
    if product["requires_telegram_id"]:
        flags.append("📱 Telegram username")
    if product["requires_email"]:
        flags.append("📧 Email address")
    if product["requires_password"]:
        flags.append("🔑 Account password")
    flags_text = "\n".join(f"  • {f}" for f in flags) if flags else "  None"
    text = (
        f"📦 <b>{html.escape(product['name'])}</b>\n\n"
        f"💰 Price: <b>{final_price:,} Tomans</b>\n\n"
        f"📋 Required info from you:\n{flags_text}"
    )
    try:
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=product_buy_keyboard(product_id)
        )
    except BadRequest:
        pass


async def shop_back_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    products = await db.get_all_products(active_only=True)
    if not products:
        try:
            await query.edit_message_text("🏪 The shop is currently empty. Check back later!")
        except BadRequest:
            pass
        return
    try:
        await query.edit_message_text(
            "🛍 <b>Shop</b>\n\nSelect a product to view its details:",
            parse_mode="HTML",
            reply_markup=shop_products_keyboard(products),
        )
    except BadRequest:
        pass

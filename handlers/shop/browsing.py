"""
handlers/shop/browsing.py — Shop menu and product detail browsing.
"""

import html

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import database as db
from keyboards import shop_products_keyboard, product_buy_keyboard
from handlers.emoji import get_all_ces


async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await db.ensure_user(update.effective_user.id)
    products = await db.get_all_products(active_only=True)
    ces = await get_all_ces()
    if not products:
        await update.message.reply_text(
            f"{ces['emoji_shop']} <b>فروشگاه آنلاین</b>\n\n"
            "❌ در حال حاضر هیچ محصولی موجود نیست.\n"
            "لطفاً بعداً دوباره امتحان کنید!",
            parse_mode="HTML",
        )
        return
    await update.message.reply_text(
        f"{ces['emoji_shop']} <b>فروشگاه آنلاین</b>\n\n"
        f"<i>{ces['emoji_fire']} بهترین و ارزان‌ترین خدمات</i>\n\n"
        "📌 <b>ویژگی‌های ما:</b>\n"
        f"  {ces['emoji_check']} پرداخت ایمن و سریع\n"
        f"  {ces['emoji_check']} تحویل فوری\n"
        f"  {ces['emoji_check']} پشتیبانی ۲۴/۷\n"
        f"  {ces['emoji_check']} تخفیف‌های ویژه\n\n"
        "👇 <b>یک محصول را انتخاب کنید:</b>",
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
            await query.edit_message_text(
                "❌ <b>محصول موجود نیست</b>\n\n"
                "این محصول دیگر در دسترس نیست. لطفاً محصول دیگری را انتخاب کنید.",
                parse_mode="HTML",
            )
        except BadRequest:
            pass
        return
    rate = await db.get_currency_rate()
    final_price = int(product["base_currency_price"] * rate) + product["admin_profit"]
    
    flags = []
    if product["requires_telegram_id"]:
        flags.append("📱 شناسه تلگرام")
    if product["requires_email"]:
        flags.append("📧 آدرس ایمیل")
    if product["requires_password"]:
        flags.append("🔑 رمز عبور")
    if product["requires_count"]:
        flags.append("🔢 تعداد/مقدار")
    
    flags_section = (
        "<b>📋 اطلاعات مورد نیاز:</b>\n" +
        "\n".join(f"  ✓ {f}" for f in flags)
    ) if flags else "<b>📋 اطلاعات مورد نیاز:</b>\n  ✓ اطلاعات اضافی نیاز نیست"

    emoji_prefix = ""
    if product.get("product_emoji_id") and product.get("product_emoji_char"):
        emoji_prefix = f'<tg-emoji emoji-id="{product["product_emoji_id"]}">{product["product_emoji_char"]}</tg-emoji> '

    text = (
        f"<b>{emoji_prefix}{html.escape(product['name'])}</b>\n\n"
        f"💰 <b>قیمت</b>: {final_price:,} تومان\n\n"
        f"{flags_section}\n\n"
        "✨ <i>پس از خرید، محصول فوری فعال می‌شود</i>"
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
    ces = await get_all_ces()
    if not products:
        try:
            await query.edit_message_text(
                f"{ces['emoji_shop']} <b>فروشگاه آنلاین</b>\n\n"
                "❌ در حال حاضر هیچ محصولی موجود نیست.",
                parse_mode="HTML",
            )
        except BadRequest:
            pass
        return
    try:
        await query.edit_message_text(
            f"{ces['emoji_shop']} <b>فروشگاه آنلاین</b>\n\n"
            f"<i>{ces['emoji_fire']} بهترین و ارزان‌ترین خدمات</i>\n\n"
            "📌 <b>ویژگی‌های ما:</b>\n"
            f"  {ces['emoji_check']} پرداخت ایمن و سریع\n"
            f"  {ces['emoji_check']} تحویل فوری\n"
            f"  {ces['emoji_check']} پشتیبانی ۲۴/۷\n"
            f"  {ces['emoji_check']} تخفیف‌های ویژه\n\n"
            "👇 <b>یک محصول را انتخاب کنید:</b>",
            parse_mode="HTML",
            reply_markup=shop_products_keyboard(products),
        )
    except BadRequest:
        pass

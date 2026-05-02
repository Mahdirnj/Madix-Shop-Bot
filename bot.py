"""
bot.py — Application entry point.

Registers all handlers and starts Long Polling.
"""

import os
import logging
from dotenv import load_dotenv

# Load environment variables FIRST — before any module that calls os.getenv()
load_dotenv()

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

import database as db
from handlers.admin import (
    admin_panel,
    manage_products,
    manage_cards,
    manage_discounts,
    pending_transactions,
    processing_orders,
    set_rate,
    admin_statistics,
    # Callback handlers
    admin_back_main,
    product_detail_callback,
    product_toggle_callback,
    product_delete_prompt_callback,
    product_delete_confirm_callback,
    card_detail_callback,
    card_toggle_callback,
    card_delete_callback,
    discount_detail_callback,
    discount_delete_callback,
    transaction_approve_callback,
    transaction_reject_callback,
    order_complete_callback,
    order_reject_callback,
    order_payment_reject_callback,
    order_approve_callback,
    rate_auto_callback,
    # Settings & Admin management
    admin_settings,
    admin_manage_admins_callback,
    remove_admin_callback,
    # Premium emoji config
    settings_emoji_callback,
    clear_emoji_slot_callback,
    # ConversationHandler builders
    build_add_product_conv,
    build_edit_product_conv,
    build_add_card_conv,
    build_set_rate_conv,
    build_add_discount_conv,
    build_broadcast_conv,
    build_set_support_conv,
    build_add_admin_conv,
    build_set_emoji_conv,
    # JobQueue callback
    auto_rate_job,
    is_admin,
)
from handlers.shop import (
    shop_menu,
    shop_product_callback,
    shop_back_list_callback,
    wallet_menu,
    wallet_topup_callback,
    wallet_history_callback,
    topup_cancel_callback,
    user_profile,
    user_support,
    build_shop_conv,
    build_topup_conv,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Startup hook — initialise the database
# ---------------------------------------------------------------------------

async def post_init(application) -> None:
    await db.init_db()
    logger.info("Database initialised.")
    from handlers.utils import refresh_admin_cache
    await refresh_admin_cache()
    logger.info("Admin cache loaded.")
    # Schedule the auto currency-rate job every 3 hours
    application.job_queue.run_repeating(
        auto_rate_job,
        interval=3 * 60 * 60,  # seconds
        first=10,               # run 10 s after startup for an early refresh
    )


# ---------------------------------------------------------------------------
# /start handler — registers the user and shows the appropriate main menu
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from keyboards import admin_main_menu_keyboard, main_menu_keyboard
    user = update.effective_user
    await db.ensure_user(user.id)
    if is_admin(user.id):
        await update.message.reply_text(
            f"👋 ادمین گرامی {user.first_name} خوش آمدید!",
            reply_markup=admin_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"👋 {user.first_name} عزیز خوش آمدید!\n\nبرای شروع خرید از منوی زیر استفاده کنید.",
            reply_markup=main_menu_keyboard(),
        )


# ---------------------------------------------------------------------------
# Admin ReplyKeyboard text router (routes button presses to handler functions)
# ---------------------------------------------------------------------------

async def admin_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes admin ReplyKeyboard button presses that are not inside a ConversationHandler."""
    text = update.message.text
    if text == "📦 مدیریت محصولات":
        await manage_products(update, context)
    elif text == "💳 مدیریت کارت‌ها":
        await manage_cards(update, context)
    elif text == "🏷 مدیریت تخفیف‌ها":
        await manage_discounts(update, context)
    elif text == "📋 تراکنش‌های در انتظار":
        await pending_transactions(update, context)
    elif text == "📦 سفارشات فعال":
        await processing_orders(update, context)
    elif text == "💰 تنظیم نرخ ارز":
        await set_rate(update, context)
    elif text == "📊 آمار و گزارشات":
        await admin_statistics(update, context)
    elif text == "⚙️ تنظیمات":
        await admin_settings(update, context)


async def user_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes user ReplyKeyboard button presses to their handlers."""
    text = update.message.text
    if text == "🛍 فروشگاه":
        await shop_menu(update, context)
    elif text == "👤 پروفایل من":
        await user_profile(update, context)
    elif text == "💰 کیف پول من":
        await wallet_menu(update, context)
    elif text == "🎧 پشتیبانی":
        await user_support(update, context)


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception:", exc_info=context.error)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set in the .env file.")

    request = HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=60.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=60.0,
    )

    app = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # ── Conversations (must be registered before plain handlers) ──────────
    app.add_handler(build_add_product_conv())
    app.add_handler(build_edit_product_conv())
    app.add_handler(build_add_card_conv())
    app.add_handler(build_set_rate_conv())
    app.add_handler(build_add_discount_conv())
    app.add_handler(build_broadcast_conv())
    app.add_handler(build_set_support_conv())
    app.add_handler(build_add_admin_conv())
    app.add_handler(build_set_emoji_conv())
    app.add_handler(build_shop_conv())
    app.add_handler(build_topup_conv())

    # ── Commands ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))

    # ── Inline callback query handlers ────────────────────────────────────
    app.add_handler(CallbackQueryHandler(admin_back_main,               pattern="^admin_back_main$"))
    app.add_handler(CallbackQueryHandler(manage_products,               pattern="^admin_product_list$"))
    app.add_handler(CallbackQueryHandler(manage_cards,                  pattern="^admin_card_list$"))
    app.add_handler(CallbackQueryHandler(manage_discounts,              pattern="^admin_discount_list$"))

    # Currency rate
    app.add_handler(CallbackQueryHandler(rate_auto_callback,            pattern="^admin_rate_auto$"))

    # Products
    app.add_handler(CallbackQueryHandler(product_detail_callback,       pattern=r"^admin_product_\d+$"))
    app.add_handler(CallbackQueryHandler(product_toggle_callback,       pattern=r"^admin_product_toggle_\d+$"))
    app.add_handler(CallbackQueryHandler(product_delete_prompt_callback, pattern=r"^admin_product_delete_\d+$"))
    app.add_handler(CallbackQueryHandler(product_delete_confirm_callback, pattern=r"^admin_product_delete_confirm_\d+$"))

    # Cards
    app.add_handler(CallbackQueryHandler(card_detail_callback,          pattern=r"^admin_card_\d+$"))
    app.add_handler(CallbackQueryHandler(card_toggle_callback,          pattern=r"^admin_card_toggle_\d+$"))
    app.add_handler(CallbackQueryHandler(card_delete_callback,          pattern=r"^admin_card_delete_\d+$"))

    # Discounts
    app.add_handler(CallbackQueryHandler(discount_delete_callback,      pattern=r"^admin_discount_delete_.+$"))
    app.add_handler(CallbackQueryHandler(discount_detail_callback,      pattern=r"^admin_discount_.+$"))

    # Transactions
    app.add_handler(CallbackQueryHandler(transaction_approve_callback,  pattern=r"^admin_tx_approve_\d+$"))
    app.add_handler(CallbackQueryHandler(transaction_reject_callback,   pattern=r"^admin_tx_reject_\d+$"))

    # Orders
    app.add_handler(CallbackQueryHandler(order_approve_callback,        pattern=r"^admin_order_approve_\d+$"))
    app.add_handler(CallbackQueryHandler(order_payment_reject_callback, pattern=r"^admin_order_payment_reject_\d+$"))
    app.add_handler(CallbackQueryHandler(order_complete_callback,       pattern=r"^admin_order_complete_\d+$"))
    app.add_handler(CallbackQueryHandler(order_reject_callback,         pattern=r"^admin_order_reject_\d+$"))

    # Settings & Admin management
    app.add_handler(CallbackQueryHandler(admin_manage_admins_callback,  pattern="^admin_settings_admins$"))
    app.add_handler(CallbackQueryHandler(remove_admin_callback,         pattern=r"^admin_rm_admin_\d+$"))
    app.add_handler(CallbackQueryHandler(settings_emoji_callback,       pattern="^admin_settings_emojis$"))
    app.add_handler(CallbackQueryHandler(clear_emoji_slot_callback,     pattern=r"^admin_emoji_clear_\w+$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern="^admin_noop$"))

    # Shop — product browsing
    app.add_handler(CallbackQueryHandler(shop_product_callback,         pattern=r"^shop_product_\d+$"))
    app.add_handler(CallbackQueryHandler(shop_back_list_callback,       pattern="^shop_back_list$"))

    # Shop — checkout & invoice actions (handled inside build_shop_conv CHECKOUT state)

    # Wallet
    app.add_handler(CallbackQueryHandler(wallet_topup_callback,         pattern="^wallet_topup$"))
    app.add_handler(CallbackQueryHandler(wallet_history_callback,       pattern="^wallet_history$"))
    app.add_handler(CallbackQueryHandler(topup_cancel_callback,         pattern="^topup_cancel$"))

    # ── ReplyKeyboard text router (admin menu buttons not in a conv) ──────
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(
            "^(📦 مدیریت محصولات|💳 مدیریت کارت‌ها|🏷 مدیریت تخفیف‌ها"
            "|📋 تراکنش‌های در انتظار|📦 سفارشات فعال|💰 تنظیم نرخ ارز"
            "|📊 آمار و گزارشات|⚙️ تنظیمات)$"
        ),
        admin_text_router,
    ))

    # ── ReplyKeyboard text router (user menu buttons) ─────────────────────
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(
            "^(🛍 فروشگاه|👤 پروفایل من|💰 کیف پول من|🎧 پشتیبانی)$"
        ),
        user_text_router,
    ))

    # ── Error handler ─────────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    logger.info("Bot started. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

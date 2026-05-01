"""
handlers/shop — User-facing shop package.

Re-exports every public symbol that bot.py expects, and provides
ConversationHandler builders that wire together the sub-modules.
"""

from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

# ── Re-exports from sub-modules ──────────────────────────────────────────────

from handlers.shop.browsing import (                                         # noqa: F401
    shop_menu,
    shop_product_callback,
    shop_back_list_callback,
)

from handlers.shop.checkout import (                                         # noqa: F401
    buy_now_callback,
    shop_get_tg_id, shop_get_email, shop_get_password, shop_get_count,
    shop_discount_callback, shop_collect_discount,
    shop_pay_card_callback, shop_collect_receipt,
    shop_pay_wallet_callback,
    shop_cancel_callback, shop_force_cancel, shop_conv_menu_exit,
)

from handlers.shop.wallet import (                                           # noqa: F401
    wallet_menu,
    wallet_topup_callback,
    topup_get_amount, topup_collect_receipt,
    topup_cancel_callback,
    wallet_history_callback,
)

from handlers.shop.profile import user_profile, user_support                 # noqa: F401

from handlers.shop._helpers import (
    COLLECT_TG_ID, COLLECT_EMAIL, COLLECT_PASSWORD, COLLECT_COUNT,
    COLLECT_DISCOUNT, COLLECT_RECEIPT, CHECKOUT,
    TOPUP_AMOUNT, TOPUP_RECEIPT,
)


# ── ConversationHandler builders ─────────────────────────────────────────────

def build_shop_conv() -> ConversationHandler:
    """
    Checkout conversation.
    Entry: shop_buy_<id>  (CallbackQuery)
    States handle input collection AND payment steps triggered by inline buttons.
    """
    menu_exit = MessageHandler(
        filters.Regex(r"^(🛍 Shop|👤 My Profile|💰 My Wallet|🎧 Support)$"),
        shop_conv_menu_exit,
    )
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(buy_now_callback, pattern=r"^shop_buy_\d+$"),
        ],
        states={
            COLLECT_TG_ID:    [MessageHandler(filters.TEXT & ~filters.COMMAND, shop_get_tg_id)],
            COLLECT_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, shop_get_email)],
            COLLECT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, shop_get_password)],
            COLLECT_COUNT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, shop_get_count)],
            COLLECT_DISCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, shop_collect_discount)],
            COLLECT_RECEIPT:  [MessageHandler(filters.PHOTO, shop_collect_receipt)],
            CHECKOUT: [
                CallbackQueryHandler(shop_discount_callback,   pattern=r"^shop_discount$"),
                CallbackQueryHandler(shop_pay_card_callback,   pattern=r"^shop_pay_card$"),
                CallbackQueryHandler(shop_pay_wallet_callback, pattern=r"^shop_pay_wallet$"),
                CallbackQueryHandler(shop_cancel_callback,     pattern=r"^shop_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", shop_force_cancel),
            CallbackQueryHandler(shop_cancel_callback, pattern=r"^shop_cancel$"),
            menu_exit,
        ],
        allow_reentry=True,
    )


def build_topup_conv() -> ConversationHandler:
    """Wallet top-up conversation. Entry: wallet_topup (CallbackQuery)."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(wallet_topup_callback, pattern="^wallet_topup$"),
        ],
        states={
            TOPUP_AMOUNT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, topup_get_amount)],
            TOPUP_RECEIPT: [MessageHandler(filters.PHOTO, topup_collect_receipt)],
        },
        fallbacks=[
            CommandHandler("cancel", shop_force_cancel),
        ],
        allow_reentry=True,
    )

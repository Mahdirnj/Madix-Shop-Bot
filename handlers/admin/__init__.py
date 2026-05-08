"""
handlers/admin — Admin panel package.

Re-exports every public symbol that bot.py expects, and provides
ConversationHandler builders that wire together the sub-modules.
"""

from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ── Re-exports from sub-modules ──────────────────────────────────────────────

from handlers.utils import is_admin                                          # noqa: F401

from handlers.admin.panel import admin_panel, admin_back_main, user_lookup, user_list_page_callback                # noqa: F401

from handlers.admin.products import (                                        # noqa: F401
    manage_products,
    product_detail_callback,
    product_toggle_callback,
    product_delete_prompt_callback,
    product_delete_confirm_callback,
    # Add product conversation handlers
    add_product_start,
    ap_get_name, ap_get_base_price, ap_get_profit,
    ap_req_tg_callback, ap_req_email_callback, ap_req_pass_callback, ap_req_count_callback,
    ap_get_description,
    AP_NAME, AP_BASE_PRICE, AP_PROFIT,
    AP_REQ_TG, AP_REQ_EMAIL, AP_REQ_PASS, AP_REQ_COUNT, AP_DESCRIPTION,
    # Edit product conversation handlers
    edit_product_start,
    ep_get_name, ep_get_base_price, ep_get_profit,
    ep_req_tg_callback, ep_req_email_callback, ep_req_pass_callback, ep_req_count_callback,
    ep_get_description,
    EP_NAME, EP_BASE_PRICE, EP_PROFIT,
    EP_REQ_TG, EP_REQ_EMAIL, EP_REQ_PASS, EP_REQ_COUNT, EP_DESCRIPTION,
)

from handlers.admin.cards import (                                           # noqa: F401
    manage_cards,
    card_detail_callback,
    card_toggle_callback,
    card_delete_callback,
    add_card_start, ac_get_number, ac_get_holder,
    AC_NUMBER, AC_HOLDER,
)

from handlers.admin.currency import (                                        # noqa: F401
    set_rate,
    rate_manual_callback,
    rate_auto_callback,
    sr_get_value,
    auto_rate_job,
    SR_VALUE,
)

from handlers.admin.discounts import (                                       # noqa: F401
    manage_discounts,
    discount_detail_callback,
    discount_delete_callback,
    add_discount_start, ad_get_code, ad_get_percent,
    AD_CODE, AD_PERCENT,
)

from handlers.admin.transactions import (                                    # noqa: F401
    pending_transactions,
    processing_orders,
    transaction_approve_callback,
    transaction_reject_callback,
    order_complete_callback,
    order_reject_callback,
    order_payment_reject_callback,
    order_approve_callback,
    rejection_reason_select_callback,
    rejection_custom_entry_callback,
    rejection_custom_receive,
    rejection_custom_cancel,
    REJECTION_CUSTOM_REASON,
)

from handlers.admin.broadcast import (                                       # noqa: F401
    broadcast_start, bc_preview, bc_confirm_send,
    BC_MESSAGE, BC_CONFIRM,
)

from handlers.admin.statistics import admin_statistics                       # noqa: F401

from handlers.admin.settings import (                                        # noqa: F401
    admin_settings,
    settings_support_callback, ss_get_handle, SS_HANDLE,
    admin_manage_admins_callback, remove_admin_callback,
    add_admin_start, aa_get_id, aa_get_name, AA_ID, AA_NAME,
    settings_emoji_callback, se_slot_callback, se_get_emoji,
    clear_emoji_slot_callback, SE_EMOJI,
    settings_min_topup_callback, sm_get_amount, SM_AMOUNT,
)

from handlers.admin._helpers import cancel_conversation as _cancel


# ── ConversationHandler builders ─────────────────────────────────────────────

def build_add_product_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(add_product_start, pattern="^admin_product_add$")],
        states={
            AP_NAME:        [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_name)],
            AP_BASE_PRICE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_base_price)],
            AP_PROFIT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_profit)],
            AP_REQ_TG:      [CallbackQueryHandler(ap_req_tg_callback, pattern="^ap_req_tg_(yes|no)$")],
            AP_REQ_EMAIL:   [CallbackQueryHandler(ap_req_email_callback, pattern="^ap_req_email_(yes|no)$")],
            AP_REQ_PASS:    [CallbackQueryHandler(ap_req_pass_callback, pattern="^ap_req_pass_(yes|no)$")],
            AP_REQ_COUNT:   [CallbackQueryHandler(ap_req_count_callback, pattern="^ap_req_count_(yes|no)$")],
            AP_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_description)],
        },
        fallbacks=[MessageHandler(filters.Regex("^\u274c \u0627\u0646\u0635\u0631\u0627\u0641$"), _cancel)],
        allow_reentry=True,
    )


def build_edit_product_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_product_start, pattern=r"^admin_product_edit_\d+$")],
        states={
            EP_NAME:        [MessageHandler(filters.TEXT & ~filters.COMMAND, ep_get_name)],
            EP_BASE_PRICE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ep_get_base_price)],
            EP_PROFIT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ep_get_profit)],
            EP_REQ_TG:      [CallbackQueryHandler(ep_req_tg_callback, pattern="^ep_req_tg_(yes|no)$")],
            EP_REQ_EMAIL:   [CallbackQueryHandler(ep_req_email_callback, pattern="^ep_req_email_(yes|no)$")],
            EP_REQ_PASS:    [CallbackQueryHandler(ep_req_pass_callback, pattern="^ep_req_pass_(yes|no)$")],
            EP_REQ_COUNT:   [CallbackQueryHandler(ep_req_count_callback, pattern="^ep_req_count_(yes|no)$")],
            EP_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ep_get_description)],
        },
        fallbacks=[MessageHandler(filters.Regex("^\u274c \u0627\u0646\u0635\u0631\u0627\u0641$"), _cancel)],
        allow_reentry=True,
    )


def build_add_card_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(add_card_start, pattern="^admin_card_add$")],
        states={
            AC_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ac_get_number)],
            AC_HOLDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ac_get_holder)],
        },
        fallbacks=[MessageHandler(filters.Regex("^\u274c \u0627\u0646\u0635\u0631\u0627\u0641$"), _cancel)],
        allow_reentry=True,
    )


def build_set_rate_conv() -> ConversationHandler:
    """Manual-entry branch of the rate conversation (auto branch uses callbacks only)."""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(rate_manual_callback, pattern="^admin_rate_manual$")],
        states={
            SR_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sr_get_value)],
        },
        fallbacks=[MessageHandler(filters.Regex("^\u274c \u0627\u0646\u0635\u0631\u0627\u0641$"), _cancel)],
        allow_reentry=True,
    )


def build_add_discount_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(add_discount_start, pattern="^admin_discount_add$")],
        states={
            AD_CODE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_code)],
            AD_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_percent)],
        },
        fallbacks=[MessageHandler(filters.Regex("^\u274c \u0627\u0646\u0635\u0631\u0627\u0641$"), _cancel)],
        allow_reentry=True,
    )


def build_broadcast_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^\U0001f4e3 \u0627\u0631\u0633\u0627\u0644 \u0647\u0645\u06af\u0627\u0646\u06cc$"), broadcast_start)],
        states={
            BC_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bc_preview)],
            BC_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, bc_confirm_send)],
        },
        fallbacks=[MessageHandler(filters.Regex("^\u274c \u0627\u0646\u0635\u0631\u0627\u0641$"), _cancel)],
        allow_reentry=True,
    )


def build_set_support_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(settings_support_callback, pattern="^admin_settings_support$")],
        states={
            SS_HANDLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ss_get_handle)],
        },
        fallbacks=[MessageHandler(filters.Regex("^\u274c \u0627\u0646\u0635\u0631\u0627\u0641$"), _cancel)],
        allow_reentry=True,
    )


def build_add_admin_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^admin_add_admin$")],
        states={
            AA_ID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_get_id)],
            AA_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, aa_get_name)],
        },
        fallbacks=[MessageHandler(filters.Regex("^\u274c \u0627\u0646\u0635\u0631\u0627\u0641$"), _cancel)],
        allow_reentry=True,
    )



def build_set_emoji_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(se_slot_callback, pattern=r"^admin_emoji_set_\w+$")],
        states={
            SE_EMOJI: [MessageHandler(filters.TEXT & ~filters.COMMAND, se_get_emoji)],
        },
        fallbacks=[MessageHandler(filters.Regex("^\u274c \u0627\u0646\u0635\u0631\u0627\u0641$"), _cancel)],
        allow_reentry=True,
    )


def build_set_min_topup_conv() -> ConversationHandler:
    """Conversation to let admins configure the minimum wallet top-up amount."""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(settings_min_topup_callback, pattern="^admin_settings_min_topup$")],
        states={
            SM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sm_get_amount)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ انصراف$"), _cancel)],
        allow_reentry=True,
    )


def build_rejection_reason_conv() -> ConversationHandler:
    """Conversation that collects a custom rejection reason typed by the admin."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                rejection_custom_entry_callback,
                pattern=r"^admin_rr_(t|op|o)_\d+_c$",
            )
        ],
        states={
            REJECTION_CUSTOM_REASON: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ انصراف$"),
                    rejection_custom_receive,
                )
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ انصراف$"), rejection_custom_cancel)
        ],
        allow_reentry=True,
    )

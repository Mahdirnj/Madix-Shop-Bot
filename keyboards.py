"""
keyboards.py — All InlineKeyboardMarkup and ReplyKeyboardMarkup builders.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


# ---------------------------------------------------------------------------
# Main menus
# ---------------------------------------------------------------------------

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        ["🛍 فروشگاه", "👤 پروفایل من"],
        ["💰 کیف پول من", "🎧 پشتیبانی"],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def admin_main_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        ["📦 مدیریت محصولات", "💳 مدیریت کارت‌ها"],
        ["💰 تنظیم نرخ ارز", "🏷 مدیریت تخفیف‌ها"],
        ["📋 تراکنش‌های در انتظار", "📦 سفارشات فعال"],
        ["📊 آمار و گزارشات", "📣 ارسال همگانی"],
        ["⚙️ تنظیمات"],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


# ---------------------------------------------------------------------------
# Admin: Settings panel
# ---------------------------------------------------------------------------

def admin_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎧 ویرایش ایدی پشتیبانی", callback_data="admin_settings_support")],
        [InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data="admin_settings_admins")],
        [InlineKeyboardButton("🌟 ایموجی‌های پریمیوم", callback_data="admin_settings_emojis")],
    ])


def admin_list_keyboard(admins: list[dict], env_ids: set) -> InlineKeyboardMarkup:
    """Show each admin with a remove button (env/master admins show a lock icon, no remove)."""
    buttons = []
    for a in admins:
        uid = a["user_id"]
        name = a["name"]
        if uid in env_ids:
            # Master admin — show lock, no remove button
            buttons.append([InlineKeyboardButton(f"🔐 {name} ({uid})", callback_data="admin_noop")])
        else:
            buttons.append([
                InlineKeyboardButton(f"👤 {name} ({uid})", callback_data="admin_noop"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"admin_rm_admin_{uid}"),
            ])
    buttons.append([InlineKeyboardButton("➕ افزودن ادمین جدید", callback_data="admin_add_admin")])
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Admin: Product management
# ---------------------------------------------------------------------------

def products_list_keyboard(products: list[dict]) -> InlineKeyboardMarkup:
    """One button per product showing name + active status, plus an Add button."""
    buttons = []
    for p in products:
        status_icon = "✅" if p["is_active"] else "❌"
        label = f"{status_icon} {p.get('product_emoji_char', '')} {p['name']}".strip()
        # normalise double spaces if no emoji
        label = " ".join(label.split())
        buttons.append([
            InlineKeyboardButton(
                label,
                callback_data=f"admin_product_{p['product_id']}",
            )
        ])
    buttons.append([InlineKeyboardButton("➕ افزودن محصول جدید", callback_data="admin_product_add")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
    return InlineKeyboardMarkup(buttons)


def product_detail_keyboard(product_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔴 غیرفعال‌سازی" if is_active else "🟢 فعال‌سازی"
    buttons = [
        [InlineKeyboardButton("✏️ ویرایش محصول", callback_data=f"admin_product_edit_{product_id}")],
        [InlineKeyboardButton(toggle_label, callback_data=f"admin_product_toggle_{product_id}")],
        [InlineKeyboardButton("🗑 حذف محصول", callback_data=f"admin_product_delete_{product_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_product_list")],
    ]
    return InlineKeyboardMarkup(buttons)


def yes_no_keyboard(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    """Inline Yes/No buttons used in boolean steps of conversations."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ بله", callback_data=yes_data),
            InlineKeyboardButton("❌ خیر", callback_data=no_data),
        ]
    ])


# ---------------------------------------------------------------------------
# Admin: Card management
# ---------------------------------------------------------------------------

def cards_list_keyboard(cards: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for c in cards:
        status_icon = "✅" if c["is_active"] else "❌"
        label = f"{status_icon} {c['card_number']}"
        if c.get("cardholder_name"):
            label += f" ({c['cardholder_name']})"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"admin_card_{c['card_id']}")
        ])
    buttons.append([InlineKeyboardButton("➕ افزودن کارت جدید", callback_data="admin_card_add")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
    return InlineKeyboardMarkup(buttons)


def card_detail_keyboard(card_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔴 غیرفعال‌سازی" if is_active else "🟢 فعال‌سازی"
    buttons = [
        [InlineKeyboardButton(toggle_label, callback_data=f"admin_card_toggle_{card_id}")],
        [InlineKeyboardButton("🗑 حذف کارت", callback_data=f"admin_card_delete_{card_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_card_list")],
    ]
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Admin: Discounts management
# ---------------------------------------------------------------------------

def discounts_list_keyboard(discounts: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for d in discounts:
        status_icon = "✅" if d["is_active"] else "❌"
        pct = d.get("percentage_discount", d.get("amount", 0))
        buttons.append([
            InlineKeyboardButton(
                f"{status_icon} {d['code']} — {pct}%",
                callback_data=f"admin_discount_view_{d['code']}",
            )
        ])
    buttons.append([InlineKeyboardButton("➕ افزودن کد تخفیف", callback_data="admin_discount_add")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
    return InlineKeyboardMarkup(buttons)


def discount_detail_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 حذف", callback_data=f"admin_discount_delete_{code}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_discount_list")],
    ])


# ---------------------------------------------------------------------------
# Admin: Transactions / Orders review
# ---------------------------------------------------------------------------

def transaction_review_keyboard(transaction_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید", callback_data=f"admin_tx_approve_{transaction_id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"admin_tx_reject_{transaction_id}"),
        ]
    ])


def order_review_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تکمیل شد", callback_data=f"admin_order_complete_{order_id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"admin_order_reject_{order_id}"),
        ]
    ])


def order_payment_review_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Used when admin reviews a PENDING_PAYMENT card order."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید پرداخت", callback_data=f"admin_order_approve_{order_id}"),
            InlineKeyboardButton("❌ رد پرداخت", callback_data=f"admin_order_payment_reject_{order_id}"),
        ]
    ])


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["❌ انصراف"]], resize_keyboard=True, one_time_keyboard=True)


def cancel_skip_keyboard() -> ReplyKeyboardMarkup:
    """Cancel + Skip buttons side-by-side for optional-edit steps."""
    return ReplyKeyboardMarkup([["❌ انصراف", "⏭ رد کردن"]], resize_keyboard=True, one_time_keyboard=True)


def broadcast_confirm_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["✅ بله، ارسال شود"], ["❌ انصراف"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def back_inline_keyboard(callback_data: str = "admin_back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=callback_data)]])


def emoji_slots_keyboard(slots: list[tuple[str, str, bool]]) -> InlineKeyboardMarkup:
    """
    Build an inline keyboard for emoji slot management.
    slots: list of (slot_key, display_label, is_configured)
    """
    rows = []
    for slot_key, label, is_set in slots:
        status = "🟢" if is_set else "⚪"
        rows.append([
            InlineKeyboardButton(f"{status} {label}", callback_data="admin_noop"),
            InlineKeyboardButton("✏️ تنظیم", callback_data=f"admin_emoji_set_{slot_key}"),
            InlineKeyboardButton("🗑 پاک", callback_data=f"admin_emoji_clear_{slot_key}"),
        ])
    return InlineKeyboardMarkup(rows)


def currency_rate_mode_keyboard() -> InlineKeyboardMarkup:
    """Shown when admin taps '💰 Set Currency Rate' — choose manual or auto."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ به‌روزرسانی دستی", callback_data="admin_rate_manual")],
        [InlineKeyboardButton("🤖 به‌روزرسانی خودکار (API)", callback_data="admin_rate_auto")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")],
    ])


# ---------------------------------------------------------------------------
# Shop: User-facing
# ---------------------------------------------------------------------------

def shop_products_keyboard(products: list[dict]) -> InlineKeyboardMarkup:
    """One button per active product in the shop listing."""
    buttons = []
    for p in products:
        emoji_prefix = p.get('product_emoji_char', '')
        label = f"{emoji_prefix} {p['name']}".strip() if emoji_prefix else p['name']
        buttons.append([InlineKeyboardButton(label, callback_data=f"shop_product_{p['product_id']}")])
    return InlineKeyboardMarkup(buttons)


def product_buy_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Shown on the product detail page — Buy Now and Back buttons."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 خرید آنلاین", callback_data=f"shop_buy_{product_id}")],
        [InlineKeyboardButton("🔙 بازگشت به فروشگاه", callback_data="shop_back_list")],
    ])


def checkout_keyboard(wallet_balance: int) -> InlineKeyboardMarkup:
    """Invoice payment options displayed after all required inputs are collected."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 پرداخت با کارت به کارت", callback_data="shop_pay_card")],
        [
            InlineKeyboardButton(
                f"💰 پرداخت از کیف پول ({wallet_balance:,} تومان)",
                callback_data="shop_pay_wallet",
            )
        ],
        [InlineKeyboardButton("🏷 وارد کردن کد تخفیف", callback_data="shop_discount")],
        [InlineKeyboardButton("❌ انصراف", callback_data="shop_cancel")],
    ])


# ---------------------------------------------------------------------------
# Phase 3: Wallet & receipt keyboards
# ---------------------------------------------------------------------------

def wallet_menu_keyboard() -> InlineKeyboardMarkup:
    """Shown when user taps '💰 My Wallet'."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ شارژ کیف پول", callback_data="wallet_topup")],
        [InlineKeyboardButton("📜 تاریخچه سفارشات", callback_data="wallet_history")],
    ])


def receipt_sent_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Shown to admin after a card-payment receipt is forwarded — for order payment."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید", callback_data=f"admin_order_approve_{order_id}"),
            InlineKeyboardButton("❌ رد",  callback_data=f"admin_order_payment_reject_{order_id}"),
        ]
    ])


def topup_receipt_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    """Shown to admin after a wallet top-up receipt is forwarded."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید", callback_data=f"admin_tx_approve_{tx_id}"),
            InlineKeyboardButton("❌ رد",  callback_data=f"admin_tx_reject_{tx_id}"),
        ]
    ])

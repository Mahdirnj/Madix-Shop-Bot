"""
keyboards.py — All InlineKeyboardMarkup and ReplyKeyboardMarkup builders.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


# ---------------------------------------------------------------------------
# Main menus
# ---------------------------------------------------------------------------

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        ["🛍 Shop", "👤 Profile"],
        ["📞 Support"],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def admin_main_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        ["📦 Manage Products", "💳 Manage Cards"],
        ["💰 Set Currency Rate", "🏷 Manage Discounts"],
        ["📋 Pending Transactions", "📋 Processing Orders"],
        ["📣 Broadcast", "👤 Profile"],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


# ---------------------------------------------------------------------------
# Admin: Product management
# ---------------------------------------------------------------------------

def products_list_keyboard(products: list[dict]) -> InlineKeyboardMarkup:
    """One button per product showing name + active status, plus an Add button."""
    buttons = []
    for p in products:
        status_icon = "✅" if p["is_active"] else "❌"
        buttons.append([
            InlineKeyboardButton(
                f"{status_icon} {p['name']}",
                callback_data=f"admin_product_{p['product_id']}",
            )
        ])
    buttons.append([InlineKeyboardButton("➕ Add New Product", callback_data="admin_product_add")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back_main")])
    return InlineKeyboardMarkup(buttons)


def product_detail_keyboard(product_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔴 Deactivate" if is_active else "🟢 Activate"
    buttons = [
        [InlineKeyboardButton("✏️ Edit Product", callback_data=f"admin_product_edit_{product_id}")],
        [InlineKeyboardButton(toggle_label, callback_data=f"admin_product_toggle_{product_id}")],
        [InlineKeyboardButton("🗑 Delete Product", callback_data=f"admin_product_delete_{product_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_product_list")],
    ]
    return InlineKeyboardMarkup(buttons)


def yes_no_keyboard(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    """Inline Yes/No buttons used in boolean steps of conversations."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes", callback_data=yes_data),
            InlineKeyboardButton("❌ No", callback_data=no_data),
        ]
    ])


def confirm_keyboard(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes", callback_data=yes_data),
            InlineKeyboardButton("❌ No", callback_data=no_data),
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
    buttons.append([InlineKeyboardButton("➕ Add New Card", callback_data="admin_card_add")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back_main")])
    return InlineKeyboardMarkup(buttons)


def card_detail_keyboard(card_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔴 Deactivate" if is_active else "🟢 Activate"
    buttons = [
        [InlineKeyboardButton(toggle_label, callback_data=f"admin_card_toggle_{card_id}")],
        [InlineKeyboardButton("🗑 Delete Card", callback_data=f"admin_card_delete_{card_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_card_list")],
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
                callback_data=f"admin_discount_{d['code']}",
            )
        ])
    buttons.append([InlineKeyboardButton("➕ Add Discount Code", callback_data="admin_discount_add")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back_main")])
    return InlineKeyboardMarkup(buttons)


def discount_detail_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Delete", callback_data=f"admin_discount_delete_{code}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_discount_list")],
    ])


# ---------------------------------------------------------------------------
# Admin: Transactions / Orders review
# ---------------------------------------------------------------------------

def transaction_review_keyboard(transaction_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin_tx_approve_{transaction_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_tx_reject_{transaction_id}"),
        ]
    ])


def order_review_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Mark Completed", callback_data=f"admin_order_complete_{order_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_order_reject_{order_id}"),
        ]
    ])


def order_payment_review_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Used when admin reviews a PENDING_PAYMENT card order."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve Payment", callback_data=f"admin_order_approve_{order_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_order_reject_{order_id}"),
        ]
    ])


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True, one_time_keyboard=True)


def back_inline_keyboard(callback_data: str = "admin_back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=callback_data)]])


def currency_rate_mode_keyboard() -> InlineKeyboardMarkup:
    """Shown when admin taps '💰 Set Currency Rate' — choose manual or auto."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Manual Update", callback_data="admin_rate_manual")],
        [InlineKeyboardButton("🤖 Auto Update (API)", callback_data="admin_rate_auto")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back_main")],
    ])

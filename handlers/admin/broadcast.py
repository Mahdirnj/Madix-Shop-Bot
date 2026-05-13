"""
handlers/admin/broadcast.py — Broadcast conversation handler.

State machine:
    BROADCAST: BC_MESSAGE → preview → BC_CONFIRM → (send to all | cancel)
"""

import asyncio
import logging

from telegram import Update
from telegram.error import RetryAfter, Forbidden, BadRequest
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from keyboards import admin_main_menu_keyboard, cancel_keyboard, broadcast_confirm_keyboard
from handlers.utils import admin_filter
from handlers.admin._helpers import cancel_conversation

logger = logging.getLogger(__name__)

# ── Conversation states ──────────────────────────────────────────────────────

BC_MESSAGE = 40
BC_CONFIRM = 41

# Minimum pause between sends (seconds) to stay well under Telegram's
# ~30 msg/sec global limit.  At 0.05 s we send ~20 msg/sec — safe headroom.
_SEND_DELAY: float = 0.05

# Context key for storing the draft message
_CTX_BC_TEXT = "bc_draft_text"


# ── Handlers ─────────────────────────────────────────────────────────────────

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not admin_filter(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📣 <b>ارسال همگانی</b>\n\nپیامی را که می‌خواهید به همه کاربران ارسال شود، بفرستید.\n<i>(پشتیبانی از کدهای HTML)</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return BC_MESSAGE


async def bc_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the draft message and ask for confirmation."""
    if update.message.text == "❌ انصراف":
        return await cancel_conversation(update, context)

    context.user_data[_CTX_BC_TEXT] = update.message.text
    user_count = await db.count_users()

    await update.message.reply_text(
        f"📣 <b>پیش‌نمایش پیام</b>\n\n"
        f"──────────────────\n"
        f"{update.message.text}\n"
        f"──────────────────\n\n"
        f"این پیام به <b>{user_count}</b> کاربر ارسال خواهد شد.\n"
        f"آیا از ارسال آن اطمینان دارید؟",
        parse_mode="HTML",
        reply_markup=broadcast_confirm_keyboard(),
    )
    return BC_CONFIRM


async def _do_broadcast(bot, admin_chat_id: int, message_text: str) -> None:
    """Send broadcast to all users in background — does not block the handler."""
    sent, failed, rate_limited = 0, 0, 0
    async for user in db.iter_users():
        try:
            await bot.send_message(
                chat_id=user["user_id"], text=message_text, parse_mode="HTML"
            )
            sent += 1
        except RetryAfter as e:
            # Telegram asked us to back off — honour it, then retry once.
            logger.warning("Broadcast rate-limited; backing off %.1f s", e.retry_after)
            rate_limited += 1
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(
                    chat_id=user["user_id"], text=message_text, parse_mode="HTML"
                )
                sent += 1
                rate_limited -= 1  # Retry succeeded — count as sent, not rate-limited
            except Exception:
                failed += 1
        except (Forbidden, BadRequest):
            # User blocked the bot or the chat_id is invalid — skip silently.
            failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(_SEND_DELAY)

    rate_limited_line = f"\n⏱ محدود شده (ارسال مجدد): {rate_limited}" if rate_limited > 0 else ""
    try:
        await bot.send_message(
            chat_id=admin_chat_id,
            text=f"📣 ارسال همگانی به پایان رسید.\n✅ موفق: {sent}\n❌ ناموفق: {failed}{rate_limited_line}",
            reply_markup=admin_main_menu_keyboard(),
        )
    except Exception:
        logger.warning("Could not deliver broadcast summary to admin %s.", admin_chat_id)


async def bc_confirm_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the Yes/No confirmation for broadcast."""
    if update.message.text != "✅ بله، ارسال شود":
        # Any other text (including "❌ انصراف") cancels the broadcast
        context.user_data.pop(_CTX_BC_TEXT, None)
        await update.message.reply_text(
            "❌ ارسال همگانی لغو شد.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return ConversationHandler.END

    message_text = context.user_data.pop(_CTX_BC_TEXT, None)
    if not message_text:
        await update.message.reply_text(
            "⚠️ پیامی یافت نشد. لطفاً دوباره شروع کنید.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📣 ارسال همگانی شروع شد. پس از اتمام، نتیجه برای شما ارسال می‌شود.",
        reply_markup=admin_main_menu_keyboard(),
    )
    # Fire-and-forget: broadcast runs in background, bot stays fully responsive.
    asyncio.create_task(
        _do_broadcast(context.bot, update.effective_chat.id, message_text)
    )
    return ConversationHandler.END

import logging
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

from telegram import CallbackQuery, InlineKeyboardMarkup, Message, Update, User
from telegram.ext import ContextTypes

from ..config import settings

logger = logging.getLogger(__name__)

HandlerFunc = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]


def _log_user_action(user: User, action: str) -> None:
    logger.info(f"User action: {action} - id={user.id} username={user.username} name={user.name} full_name={user.full_name}")


def authorized(func: HandlerFunc) -> HandlerFunc:
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            return
        if str(user.id) not in settings.ALLOWED_USERS:
            if update.callback_query:
                _ = await update.callback_query.answer("You are not authorized.", show_alert=True)
            elif update.message:
                _ = await update.message.reply_text("You are not authorized to use this bot.")
            logger.warning(f"Unauthorized access attempt by user: id={user.id} username={user.username} name={user.name} full_name={user.full_name}")
            return
        _log_user_action(user, func.__name__)
        return await func(update, context)
    return wrapper


async def try_edit_text(
    target: Message | CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        if isinstance(target, Message):
            _ = await target.edit_text(text, reply_markup=reply_markup)
        else:
            _ = await target.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message: {e}")

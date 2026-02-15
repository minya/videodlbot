import logging
from functools import wraps
from telegram import Message, Update, User
from telegram.ext import ContextTypes

from ..config import settings

logger = logging.getLogger(__name__)


def _log_user_action(user: User, action: str) -> None:
    logger.info(f"User action: {action} - id={user.id} username={user.username} name={user.name} full_name={user.full_name}")


def authorized(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            return
        if str(user.id) not in settings.ALLOWED_USERS:
            if update.callback_query:
                await update.callback_query.answer("You are not authorized.", show_alert=True)
            elif update.message:
                await update.message.reply_text("You are not authorized to use this bot.")
            logger.warning(f"Unauthorized access attempt by user: id={user.id} username={user.username} name={user.name} full_name={user.full_name}")
            return
        _log_user_action(user, f"{func.__name__}")
        return await func(update, context)
    return wrapper


async def try_edit_text(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except Exception as e:
        logger.error(f"Error editing message: {e}")

from telegram import Update
from telegram.ext import ContextTypes

from .common import authorized


@authorized
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context # Unused parameter
    if update.message is None:
        return

    user = update.effective_user
    assert user is not None

    await update.message.reply_html(
        f"Hi {user.mention_html()}!\n\n"
        f"I can download videos from YouTube, Instagram, and Twitter/X.\n"
        f"Just send me a valid video URL, and I'll download it for you."
    )

from telegram import Update
from telegram.ext import ContextTypes

from .common import authorized


@authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context # Unused parameter
    if update.message is None:
        return

    await update.message.reply_text(
        "How to use this bot:\n\n"
        "1. Send a video URL from YouTube, Instagram, or Twitter/X.\n"
        "2. Wait for the bot to download and send the video.\n\n"
        "Commands:\n"
        "/start - Show welcome message\n"
        "/help - Show this help message\n"
        "/listfiles - List all files in cloud storage (with delete buttons)\n\n"
        "Note: Videos larger than 50MB will be uploaded to cloud storage and a download link will be provided."
    )

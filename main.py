import logging
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from src.videodlbot.config import settings
from src.videodlbot.utils import BYTES_MB
from src.videodlbot.storage import initialize_firebase
from src.videodlbot.bot import start, help_command, process_url, list_files, delete_file_callback

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if settings.DEBUG_MODE:
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
else:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger.setLevel(logging.INFO)


async def setup_bot_commands(application: Application) -> None:
    """Set up the bot's command menu."""
    commands = [
        BotCommand("start", "Show welcome message"),
        BotCommand("help", "Show help and usage instructions"),
        BotCommand("listfiles", "List files in cloud storage"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands menu configured")


def main() -> None:
    if not settings.BOT_TOKEN:
        logger.error("No bot token provided. Please set TELEGRAM_BOT_TOKEN in .env file.")
        return

    initialize_firebase()

    application = Application.builder().token(settings.BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("listfiles", list_files))
    application.add_handler(CallbackQueryHandler(delete_file_callback, pattern="^del:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_url))

    # Set up bot commands menu
    application.post_init = setup_bot_commands

    logger.info("Bot started. Press Ctrl+C to stop.")
    logger.info(f"Debug mode: {settings.DEBUG_MODE}")
    if settings.DEBUG_MODE:
        logger.info("Debug mode is enabled. Verbose logging will be used.")

    logger.info("Max file size for downloads: %d MB", settings.MAX_FILE_SIZE // BYTES_MB)
    logger.info("Allowed users: %s", ', '.join(settings.ALLOWED_USERS) if settings.ALLOWED_USERS else "None")
    logger.info("Use cookie: %s", "Yes" if settings.COOKIE_FILE else "No")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

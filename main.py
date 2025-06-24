import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.videodlbot.config import settings
from src.videodlbot.utils import BYTES_MB
from src.videodlbot.storage import initialize_firebase
from src.videodlbot.bot import start, help_command, process_url

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


def main() -> None:
    if not settings.BOT_TOKEN:
        logger.error("No bot token provided. Please set TELEGRAM_BOT_TOKEN in .env file.")
        return

    initialize_firebase()

    application = Application.builder().token(settings.BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_url))

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

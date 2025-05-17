import os
import logging
import tempfile
from typing import Optional, Dict, Any
import validators
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
from test.re_tests import u

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 500000000))  # Default: 500MB

# Supported platforms
SUPPORTED_PLATFORMS = ['youtube', 'instagram', 'twitter', 'x.com']

def is_valid_url(url: str) -> bool:
    """Check if the provided URL is valid."""
    return validators.url(url)

def is_supported_platform(url: str) -> bool:
    """Check if the URL belongs to a supported platform."""
    for platform in SUPPORTED_PLATFORMS:
        if platform in url.lower():
            return True
    return False

def extract_video_info(url: str) -> Dict[str, Any]:
    """Extract video information using yt-dlp."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        #'format': 'best[filesize<50M]/best',  # Prefer videos smaller than 50MB
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"Video information extracting: {url}")
        info = ydl.extract_info(url, download=False)
        return info

def download_video(url: str, output_path: str) -> Optional[str]:
    """Download video using yt-dlp."""
    try:
        ydl_opts = {
            #'format': 'best[filesize<50M]/best',  # Prefer videos smaller than 50MB
            'outtmpl': {
                'default': output_path,
            },
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            return output_path
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}!\n\n"
        f"I can download videos from YouTube, Instagram, and Twitter/X.\n"
        f"Just send me a valid video URL, and I'll download it for you."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "How to use this bot:\n\n"
        "1. Send a video URL from YouTube, Instagram, or Twitter/X.\n"
        "2. Wait for the bot to download and send the video.\n\n"
        "Note: Due to Telegram limitations, videos larger than 50MB cannot be sent."
    )

async def process_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process the URL and download the video."""
    url = update.message.text.strip()

    # Check if URL is valid
    if not is_valid_url(url):
        await update.message.reply_text("Please provide a valid URL.")
        return

    # Check if platform is supported
    if not is_supported_platform(url):
        await update.message.reply_text(
            "Sorry, this URL is not from a supported platform.\n"
            "I can download videos from YouTube, Instagram, and Twitter/X."
        )
        return

    status_message = await update.message.reply_text("Downloading video, please wait...")

    try:
        # Extract video information
        info = extract_video_info(url)

        # Check file size
        if 'filesize' in info and info['filesize'] and info['filesize'] > MAX_FILE_SIZE:
            await status_message.edit_text(
                f"Sorry, the video is too large to send via Telegram "
                f"(size: {info['filesize'] // 1000000}MB, max: {MAX_FILE_SIZE // 1000000}MB)."
            )
            return

        # Create temporary file for download
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = temp_file.name
        print(f"Temporary file created: {temp_path}")

        # Download video
        output_path = download_video(url, temp_path)

        if not output_path or not os.path.exists(output_path):
            await status_message.edit_text("Sorry, there was an error downloading the video.")
            return
        
        print(f"Video downloaded to: {output_path}")

        # Check if file exists and size is within limits
        if os.path.getsize(output_path) > MAX_FILE_SIZE:
            await status_message.edit_text(
                f"Sorry, the downloaded video is too large to send via Telegram "
                f"(size: {os.path.getsize(output_path) // 1000000}MB, max: {MAX_FILE_SIZE // 1000000}MB)."
            )
            os.unlink(output_path)
            return

        # Send video
        await status_message.edit_text("Upload in progress...")

        caption = f"Title: {info.get('title', 'Unknown')}\nSource: {url}"
        with open(output_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=caption,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120
            )

        # Cleanup
        os.unlink(output_path)
        await status_message.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await status_message.edit_text(f"An error occurred: {str(e)}")

def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("No bot token provided. Please set TELEGRAM_BOT_TOKEN in .env file.")
        return

    # Create the Application and pass it your bot's token
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Add message handler for URLs
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_url))

    # Start the Bot
    logger.info("Bot started. Press Ctrl+C to stop.")

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

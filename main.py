import os
import logging
import tempfile
import shutil
import time
import threading
from typing import Optional, Dict, Any
import validators
from dotenv import load_dotenv
from telegram import Message, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

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
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 50*1024*1024))  # Default to 50MB
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
ALLOWED_USERS = os.getenv('ALLOWED_USERS', '').split(',')

if DEBUG_MODE:
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
else:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger.setLevel(logging.INFO)

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
        logger.info(f"Video information extracting: {url}")
        info = ydl.extract_info(url, download=False)
        return info

def download_video(url: str, output_path: str, progress_data: dict) -> Optional[str]:
    """Download video using yt-dlp (synchronous function)."""
    verbose = DEBUG_MODE
    format_selection = 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best/bestvideo+bestaudio'
    
    # This progress hook captures download info in the shared progress_data dictionary
    def on_progress(d):
        # Update the shared progress data with a copy of the dictionary to avoid reference issues
        progress_data.clear()
        progress_data.update(d.copy())
        
        if d['status'] == 'finished':
            logger.info(f"Done downloading video: {d.get('filename', 'unknown')} {d.get('_total_bytes_str', 'N/A')}")
        elif d['status'] == 'downloading':
            logger.debug(f"Downloading: {d.get('_percent_str', 'N/A')} at {d.get('_speed_str', 'N/A')}")
        elif d['status'] == 'error':
            logger.error(f"Error downloading: {d.get('error', 'Unknown error')}")
    
    try:
        ydl_opts = {
            'quiet': not verbose,
            'no_warnings': not verbose,
            'verbose': verbose,
            'format': format_selection,
            'age_limit': 21,
            'geo_bypass': True,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'progress_hooks': [on_progress],
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]  # Ensure output is in mp4 format
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Starting download to: {output_path}")
            ydl.download([url])
            logger.info(f"Download completed. Checking file: {output_path}")
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path  # Return the path to the downloaded file
            else:
                logger.warning("Downloaded file is empty or does not exist")
                return None
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
    user = update.effective_user
    if str(user.id) not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        logger.warning(f"Unauthorized access attempt by user: {user.id}")
        return

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

        # Create temporary directory for download
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, "downloaded_video.mp4")
        logger.info(f"Temporary directory created: {temp_dir}. Will download to: {temp_path}")

        # Create a thread to download the video
        download_complete = threading.Event()
        download_result = [None]  # Use a list to store the result from the thread
        download_error = [None]   # Use a list to store any exception from the thread
        progress_data = {}        # Shared dictionary to store progress information
        
        def download_thread():
            try:
                result = download_video(url, temp_path, progress_data)
                download_result[0] = result
            except Exception as e:
                logger.error(f"Error in download thread: {e}")
                download_error[0] = e
            finally:
                download_complete.set()
        
        # Start the download in a separate thread
        thread = threading.Thread(target=download_thread)
        thread.daemon = True  # Make thread daemon so it doesn't block program exit
        thread.start()
        
        # Update status message periodically while downloading
        try:
            last_update_time = 0
            while not download_complete.is_set():
                # Avoid updating the message too frequently (rate limiting)
                current_time = time.time()
                if current_time - last_update_time >= 1.5:  # Update every 1.5 seconds
                    last_update_time = current_time
                    
                    # Get progress info from the shared dictionary
                    status = progress_data.get('status', '')
                    
                    if not progress_data:
                        # No progress data yet, check if file exists and show size
                        if os.path.exists(temp_path):
                            file_size = os.path.getsize(temp_path) / (1024 * 1024)  # Size in MB
                            await status_message.edit_text(f"Downloading... {file_size:.2f} MB downloaded")
                    elif status == 'downloading':
                        logger.debug(f"Progress data: {progress_data}")
                        percent = progress_data.get('_percent_str', 'N/A')
                        speed = progress_data.get('_speed_str', 'N/A')
                        eta = progress_data.get('_eta_str', '')
                        filename = progress_data.get('filename', 'video')
                        
                        message = f"Downloading {os.path.basename(filename)}...\n"
                        message += f"Progress: {percent} at {speed}\n"
                        if eta:
                            message += f"ETA: {eta}"
                        
                        await status_message.edit_text(message)
                    elif status == 'finished':
                        await status_message.edit_text("Download complete. Processing video...")
                    
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.warning("Download status updates were cancelled")
            raise
        except Exception as e:
            logger.error(f"Error while updating status: {e}")
        
        # Wait for thread to complete if it hasn't already
        if thread.is_alive():
            thread.join(timeout=5)  # Wait up to 5 seconds for thread to finish
            
        # Check if there was an error in the download thread
        if download_error[0]:
            raise download_error[0]
            
        # Get the result from the thread
        output_path = download_result[0]
        
        if not output_path or not os.path.exists(output_path):
            await status_message.edit_text("Sorry, there was an error downloading the video.")
            return

        logger.info(f"Video downloaded to: {output_path}")

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
        shutil.rmtree(temp_dir)  # Remove the temporary directory and all contents
        await status_message.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await status_message.edit_text(f"An error occurred: {str(e)}")

        # Cleanup in case of error
        try:
            # Cancel any running thread if it's still active
            if 'thread' in locals() and thread.is_alive():
                logger.info("Waiting for download thread to finish...")
                thread.join(timeout=2)  # Give it a short time to finish
                
            # Clean up files
            if 'output_path' in locals() and output_path and os.path.exists(output_path):
                os.unlink(output_path)
            if 'temp_dir' in locals() and temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup after exception: {cleanup_error}")

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
    logger.info(f"Debug mode: {DEBUG_MODE}")
    if DEBUG_MODE:
        logger.info("Debug mode is enabled. Verbose logging will be used.")

    logger.info("Max file size for downloads: %d MB", MAX_FILE_SIZE // (1024 * 1024))
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

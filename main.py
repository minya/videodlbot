import os
import logging
import tempfile
import shutil
import time
import threading
import uuid
from typing import Optional, Dict, Any
import validators
from dotenv import load_dotenv
from telegram import Message, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
import yt_dlp
import firebase_admin
from firebase_admin import credentials, storage

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# Load environment variables
load_dotenv()

# constants
COOKIE_FILE = '.secrets/cookies.txt' if os.path.exists('.secrets/cookies.txt') else None
BYTES_MB=1048576
MAX_TELEGRAM_FILE_SIZE = 50 * BYTES_MB  # 50MB for Telegram file size limit

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
_MAX_FILE_SIZE_STR = os.getenv('MAX_FILE_SIZE', '')
MAX_FILE_SIZE = int(_MAX_FILE_SIZE_STR) * BYTES_MB if _MAX_FILE_SIZE_STR else 500 * BYTES_MB  # Default to 500MB
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
ALLOWED_USERS = os.getenv('ALLOWED_USERS', '').split(',')

# Firebase configuration
FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH')
FIREBASE_STORAGE_BUCKET = os.getenv('FIREBASE_STORAGE_BUCKET')
if DEBUG_MODE:
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
else:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger.setLevel(logging.INFO)

# Initialize Firebase
firebase_app = None
if FIREBASE_CREDENTIALS_PATH and FIREBASE_STORAGE_BUCKET:
    try:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_app = firebase_admin.initialize_app(cred, {
            'storageBucket': FIREBASE_STORAGE_BUCKET
        })
        logger.info("Firebase initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Firebase: {e}")
else:
    logger.warning("Firebase credentials or bucket not configured")


def is_valid_url(url: str) -> bool:
    """Check if the provided URL is valid."""
    return validators.url(url)

EXTRACTORS = yt_dlp.extractor.list_extractors()

async def try_edit_text(message: Message, text: str) -> None:
    """Try to edit the message text, handling potential exceptions."""
    try:
        await message.edit_text(text)
    except Exception as e:
        logger.error(f"Error editing message: {e}")

def is_supported_platform(url: str) -> bool:
    for ext in EXTRACTORS:
        if ext.suitable(url):
            return True
    return False

def upload_to_firebase(file_path: str, filename: str) -> Optional[str]:
    """Upload file to Firebase Storage and return download URL."""
    if not firebase_app:
        logger.error("Firebase not initialized")
        return None
    
    try:
        bucket = storage.bucket()
        blob = bucket.blob(f"videos/{filename}")
        
        logger.info(f"Uploading {file_path} to Firebase Storage as {filename}")
        blob.upload_from_filename(file_path)
        
        # Make the blob publicly readable
        blob.make_public()
        
        download_url = blob.public_url
        logger.info(f"File uploaded successfully. Download URL: {download_url}")
        return download_url
        
    except Exception as e:
        logger.error(f"Error uploading to Firebase: {e}")
        return None

format_selection = 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best/bestvideo+bestaudio'

def extract_video_info(url: str) -> Dict[str, Any]:
    """Extract video information using yt-dlp."""
    ydl_opts = {
        'age_limit': 21,
        'cookiefile': COOKIE_FILE,
        'extract_flat': True,
        'format': format_selection,
        'geo_bypass': True,
        'no_warnings': True,
        'quiet': True,
        'verbose': DEBUG_MODE,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logger.info(f"Video information extracting: {url}")
        info = ydl.extract_info(url, download=False)
        return info

def need_convert_vcodec(vcodec: str) -> bool:
    """Check if the video codec needs conversion."""
    if not vcodec:
        return True
    if vcodec.startswith('avc1'):
        vcodec = 'h264'
    elif vcodec.startswith('av01'):
        vcodec = 'av01'
    elif vcodec.startswith('hvc1'):
        vcodec = 'h265'
    elif vcodec.startswith('hevc'):
        vcodec = 'h265'
    elif vcodec.startswith('h264'):
        vcodec = 'h264'
    elif vcodec.startswith('h265'):
        vcodec = 'h265'
    return vcodec not in ['h264', 'h265', 'avc1', 'av01']

def need_convert_acodec(acodec: str) -> bool:
    """Check if the audio codec needs conversion."""
    return acodec not in ['aac', 'mp4a.40.2', 'mp4a.40.5', 'mp4a.40.29']

def download_video(url: str, info: dict[str, any], output_path: str, progress_data: dict) -> Optional[str]:
    """Download video using yt-dlp (synchronous function)."""
    
    # This progress hook captures download info in the shared progress_data dictionary
    def on_progress(d):
        progress_data.clear()
        progress_data.update({ 'download_progress': d.copy() })

    def on_postprocess(d):
        progress_data.clear()
        progress_data.update({ 'postprocess_progress': d.copy() })

    vcodec = info.get('vcodec', '')
    acodec = info.get('acodec', '')
    extractor = info.get('extractor', '')

    need_convert = \
        extractor == 'youtube' and \
        (need_convert_vcodec(vcodec) or \
        need_convert_acodec(acodec))

    logger.info(f"Video codec: {vcodec}, Audio codec: {acodec}, Extractor: {extractor} Need convert: {need_convert}")
    verbose = DEBUG_MODE
    try:
        ydl_opts = {
            'quiet': not verbose,
            'no_warnings': not verbose,
            'verbose': verbose,
            'format': format_selection,
            'age_limit': 21,
            'geo_bypass': True,
            'cookiefile': COOKIE_FILE,
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'progress_hooks': [on_progress],
            'postprocessor_hooks': [on_postprocess],
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                },
            ],
        }

        if need_convert:
            ydl_opts['postprocessors'].append({
                    'key': 'FFmpegCopyStream',
            })
            v_a = 'libx264' if need_convert_vcodec(vcodec) else 'copy'
            c_a = 'aac' if need_convert_acodec(acodec) else 'copy'
            ydl_opts['postprocessor_args'] = {
                'copystream': [
                    '-c:v', f'{v_a}',
                    '-c:a', f'{c_a}',
                ],
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
        "Note: Videos larger than 50MB will be uploaded to cloud storage and a download link will be provided."
    )

def build_download_progress_message(progress_data: dict) -> str:
    """Build a formatted message for download progress."""
    total_bytes = progress_data.get('total_bytes', 0)
    downloaded_bytes = progress_data.get('downloaded_bytes', 0)
    eta = progress_data.get('eta', 0)
    filename = os.path.basename(progress_data.get('filename', 'video'))
    speed = progress_data.get('speed', None)
    speed_mbps = (speed / BYTES_MB) if speed else 0
    speed_mbps_str = f"{speed_mbps:.2f} MiB/s" if speed_mbps > 0 else "N/A"

    percent = (downloaded_bytes / total_bytes * 100) if total_bytes > 0 else 0
    return (f"Downloading {filename}...\t[{percent:.2f}%]\n"
            f"Downloaded: {downloaded_bytes / BYTES_MB:.2f} MiB at {speed_mbps_str}\n"
            f"Total: {total_bytes / BYTES_MB:.2f} MiB\n"
            f"ETA: {eta:.0f} seconds")

def build_pp_progress_message(progress_data: dict) -> str:
    status = progress_data.get('status', 'unknown status')
    postprocessor = progress_data.get('postprocessor', 'unknown postprocessor')
    message = f"Postprocessing with {postprocessor}...\nStatus: {status}"
    return message

async def process_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if str(user.id) not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        logger.warning(f"Unauthorized access attempt by user: {user.id} {user.username} {user.full_name}")
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
            await try_edit_text(status_message,
                f"Sorry, the video is too large"
                f"(size: {info['filesize'] // BYTES_MB}MB, max: {MAX_FILE_SIZE // BYTES_MB}MB supported)."
            )
            return

        # Create temporary directory for download
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, "video.mp4")
        logger.info(f"Temporary directory created: {temp_dir}. Will download to: {temp_path}")

        # Create a thread to download the video
        download_complete = threading.Event()
        download_result = [None]  # Use a list to store the result from the thread
        download_error = [None]   # Use a list to store any exception from the thread
        progress_data = {}        # Shared dictionary to store progress information
        
        def download_thread():
            try:
                result = download_video(url, info, temp_path, progress_data)
                download_result[0] = result
            except Exception as e:
                logger.error(f"Error in download thread: {e}")
                download_error[0] = e
            finally:
                logger.info("Download thread completed")
                download_complete.set()
        
        # Start the download in a separate thread
        thread = threading.Thread(target=download_thread)
        thread.daemon = True  # Make thread daemon so it doesn't block program exit
        thread.start()

        prev_message = ''
        # Update status message periodically while downloading
        try:
            last_update_time = 0
            while not download_complete.is_set():
                # Avoid updating the message too frequently (rate limiting)
                current_time = time.time()
                if current_time - last_update_time >= 1.5:  # Update every 1.5 seconds
                    last_update_time = current_time
                    message = ''
                    
                    if 'download_progress' in progress_data:
                        dl_progress_data = progress_data.get('download_progress', {})
                        status = dl_progress_data.get('status', '')
                        
                        if not dl_progress_data:
                            # No progress data yet, check if file exists and show size
                            if os.path.exists(temp_path):
                                file_size = os.path.getsize(temp_path) / (1024 * 1024)  # Size in MB
                                message = f"Downloading... {file_size:.2f} MB downloaded"
                        elif status == 'downloading':
                            logger.debug(f"Progress data: {dl_progress_data}")
                            message = build_download_progress_message(dl_progress_data)
                            
                        elif status == 'finished':
                            message = "Download complete. Processing video..."
                    elif 'postprocess_progress' in progress_data:
                        pp_progress_data = progress_data.get('postprocess_progress', {})
                        message = build_pp_progress_message(pp_progress_data)

                    if prev_message != message:
                        await try_edit_text(status_message, message)
                        prev_message = message
                    
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
            await try_edit_text(status_message, "Sorry, there was an error downloading the video.")
            return

        logger.info(f"Video downloaded to: {output_path}")

        # Check if file exists and size is within limits
        file_size = os.path.getsize(output_path)
        if file_size > MAX_TELEGRAM_FILE_SIZE:
            # Upload to Firebase Storage instead
            await status_message.edit_text("File too large for Telegram. Uploading to cloud storage...")
            
            # Generate a unique filename
            unique_filename = f"{uuid.uuid4()}_{info.get('title', 'video').replace(' ', '_')}.mp4"
            
            # Upload to Firebase
            download_url = upload_to_firebase(output_path, unique_filename)
            
            if download_url:
                caption = (f"Title: {info.get('title', 'Unknown')}\n"
                          f"Size: {file_size // BYTES_MB}MB (too large for Telegram)\n"
                          f"Download: {download_url}\n"
                          f"Source: {url}")
                await update.message.reply_text(caption)
            else:
                await status_message.edit_text(
                    f"Sorry, failed to upload the video to cloud storage. "
                    f"The video is {file_size // BYTES_MB}MB which exceeds Telegram's {MAX_TELEGRAM_FILE_SIZE // BYTES_MB}MB limit."
                )
            
            os.unlink(output_path)
            shutil.rmtree(temp_dir)
            await status_message.delete()
            return

        # Send video
        await try_edit_text(status_message, "Upload in progress...")

        caption = f"Title: {info.get('title', 'Unknown')}\nSource: {url}"

        width = info.get('width', None)
        height = info.get('height', None)

        with open(output_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=caption,
                width=width,
                height=height,
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
        await try_edit_text(status_message, f"An error occurred: {str(e)}")

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

    logger.info("Max file size for downloads: %d MB", MAX_FILE_SIZE // (BYTES_MB))
    logger.info("Allowed users: %s", ', '.join(ALLOWED_USERS) if ALLOWED_USERS else "None")
    logger.info("Use cookie: %s", "Yes" if COOKIE_FILE else "No")
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

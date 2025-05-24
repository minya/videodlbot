import os
import logging
import tempfile
import shutil
import time
import threading
from typing import Optional, Dict, Any, List
import validators
from dotenv import load_dotenv
from telegram import Message, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import asyncio
import yt_dlp

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


# Define format types
FORMAT_TYPE_VIDEO = 'video'
FORMAT_TYPE_AUDIO = 'audio'

def is_valid_url(url: str) -> bool:
    """Check if the provided URL is valid."""
    return validators.url(url)

EXTRACTORS = yt_dlp.extractor.list_extractors()

def is_supported_platform(url: str) -> bool:
    for ext in EXTRACTORS:
        if ext.suitable(url):
            return True
    return False

def extract_video_info(url: str) -> Dict[str, Any]:
    """Extract video information using yt-dlp."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'listformats': True,  # Get format information
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logger.info(f"Full video information extracting (for formats): {url}")
        # Add noplaylist to ensure only single video info is processed
        ydl_opts['noplaylist'] = True
        info = ydl.extract_info(url, download=False)
        return info

def download_video(url: str, output_path: str, progress_data: dict, format_id: str = None, is_audio_only: bool = False) -> Optional[str]:
    """Download video using yt-dlp (synchronous function)."""
    verbose = DEBUG_MODE

    if is_audio_only:
        # If a specific audio format ID is provided, use it.
        # Otherwise, default to the best available audio.
        format_selection = format_id if format_id else 'bestaudio/best'
    else:
        # For video, if a specific video format ID is provided (e.g., from user selection),
        # combine it with the best available audio stream to ensure sound.
        # Otherwise (e.g., direct download of 'best'), default to best video with best audio.
        format_selection = f"{format_id}" if format_id else 'bestvideo+bestaudio/best'

    logger.info(f"Using format selection: {format_selection}, Audio only: {is_audio_only}")

    # This progress hook captures download info in the shared progress_data dictionary
    def on_progress(d):
        # Update the shared progress data with a copy of the dictionary to avoid reference issues
        progress_data.clear()
        progress_data.update(d.copy())

        if d['status'] == 'finished':
            logger.info(f"Done downloading: {d.get('filename', 'unknown')} {d.get('_total_bytes_str', 'N/A')}")
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
            'noplaylist': True,  # Ensure only the specified video is downloaded
        }
        
        # Configure postprocessors based on format type
        if is_audio_only:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Starting download to: {output_path}")
            ydl.download([url])
            logger.info(f"Download completed. Checking file: {output_path}")

            # Check if file exists
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path  # Return the path to the downloaded file
            else:
                logger.warning("Downloaded file is empty or does not exist")
                return None
    except Exception as e:
        logger.error(f"Error downloading: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    # Clear any previous session data
    context.user_data.clear()

    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}!\n\n"
        f"I can download videos from YouTube, Instagram, and Twitter/X.\n"
        f"Just send me a valid video URL, and I'll show you available format options to download."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "How to use this bot:\n\n"
        "1. Send a video URL from YouTube, Instagram, or Twitter/X.\n"
        "2. The bot will show you all available formats for that URL.\n"
        "3. Choose a format by clicking the corresponding button.\n"
        "4. Wait for the bot to download and send the media.\n\n"
        "Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n\n"
        "Note: Due to Telegram limitations, videos larger than 50MB cannot be sent."
    )

async def process_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process the URL and prepare format selection options."""
    user = update.effective_user
    if str(user.id) not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        logger.warning(f"Unauthorized access attempt by user: {user.id}")
        return

    # Clear any existing session data
    context.user_data.clear()

    url = update.message.text.strip()
    # Store URL in user data first thing
    context.user_data['current_url'] = url

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

    status_message = await update.message.reply_text("Fetching available formats, please wait...")

    try:
        # Extract video information. extract_video_info now uses noplaylist=True
        info = await asyncio.to_thread(extract_video_info, url)

        if not info:
            await status_message.edit_text(
                "Sorry, couldn't extract information from this URL. "
                "It might be a playlist or an unsupported link. Please try a direct link to a single video."
            )
            return

        # Check if yt-dlp, despite noplaylist=True, still identified the content as a playlist
        # or if the URL was a generic playlist that couldn't be resolved to a single video.
        # A single video (even from a playlist URL like youtube.com/watch?v=...&list=...)
        # processed with noplaylist=True should not have _type='playlist'
        # and typically wouldn't have an 'entries' list with multiple items.
        # If 'entries' exists and has only 1 item, it's usually the video itself.

        is_playlist_type = info.get('_type') == 'playlist'
        # Some single videos might be returned as an 'entries' list with one item.
        # We consider it a playlist if there are multiple entries.
        has_multiple_entries = 'entries' in info and \
                               isinstance(info.get('entries'), list) and \
                               len(info.get('entries', [])) > 1

        if is_playlist_type or has_multiple_entries:
            logger.warning(f"URL resolved as playlist or multi-entry structure despite noplaylist=True: {url}. Info type: {info.get('_type')}")
            await status_message.edit_text(
                "It looks like this URL refers to a playlist or I couldn't isolate a single video from it. "
                "I can only process individual video URLs.\n\n"
                "If you're trying to download a specific video from a playlist, "
                "please ensure the URL directly points to that video (e.g., includes 'v=VIDEO_ID' for YouTube)."
            )
            return

        title = info.get('title', 'Unknown Video')

        # Store video info in context for later use
        context.user_data['video_info'] = info

        # Check if formats are available
        if 'formats' not in info or not info['formats']:
            # Start the download directly with best quality
            await status_message.edit_text("No format information available. Starting download with best quality...")
            context.user_data['format_id'] = None  # Use default/best
            context.user_data['is_audio_only'] = False
            await download_and_send_video(update, context, url, status_message)
            return

        # If only one format is available, download it directly
        if len(info['formats']) == 1:
            await status_message.edit_text("Only one format available. Starting download...")
            context.user_data['format_id'] = info['formats'][0].get('format_id')
            context.user_data['is_audio_only'] = False
            await download_and_send_video(update, context, url, status_message)
            return

        # Get available formats
        formats = info.get('formats', [])

        # Filter out formats without essential info
        formats = [f for f in formats if f.get('format_id')]

        # Separate audio and video formats
        video_formats = [f for f in formats if f.get('vcodec') != 'none']
        audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']

        # Function to get height for sorting
        def get_height(fmt):
            height = fmt.get('height', 0)
            if not height and 'resolution' in fmt:
                # Try to extract height from resolution string (e.g. "1920x1080")
                try:
                    resolution = fmt.get('resolution', '')
                    if 'x' in resolution:
                        height = int(resolution.split('x')[1])
                except:
                    pass
            return height or 0

        # Prepare keyboard for format selection
        keyboard = []

        # Add video formats
        if video_formats:
            # Sort videos by height (resolution) first, then by filesize as tie-breaker
            video_formats.sort(key=lambda x: (get_height(x), x.get('filesize', 0) if x.get('filesize') else 0), reverse=True)

            # Add header for video formats
            keyboard.append([InlineKeyboardButton("🎬 Video Formats", callback_data="h")])

            # Filter unique resolution formats to reduce clutter
            unique_video_formats = []
            seen_resolutions = set()

            for fmt in video_formats:
                height = get_height(fmt)
                res_key = f"{height}_{fmt.get('ext', '')}"

                if res_key not in seen_resolutions:
                    seen_resolutions.add(res_key)
                    unique_video_formats.append(fmt)

            # Limit to max 8 video formats to avoid too many buttons
            if len(unique_video_formats) > 8:
                # Select representative formats across the quality spectrum
                step = len(unique_video_formats) // 8
                selected_video_formats = [unique_video_formats[i] for i in range(0, len(unique_video_formats), step)]
                if len(selected_video_formats) < 8:
                    # Add highest and lowest if not already included
                    if unique_video_formats[0] not in selected_video_formats:
                        selected_video_formats.insert(0, unique_video_formats[0])
                    if unique_video_formats[-1] not in selected_video_formats:
                        selected_video_formats.append(unique_video_formats[-1])
                # Limit to 8
                selected_video_formats = selected_video_formats[:8]
            else:
                selected_video_formats = unique_video_formats

            # Create buttons for video formats (2 per row)
            row = []
            for fmt in selected_video_formats:
                format_id = fmt.get('format_id', '')
                height = get_height(fmt)
                ext = fmt.get('ext', 'mp4')

                # Get filesize if available
                filesize = fmt.get('filesize')
                if not filesize and fmt.get('filesize_approx'):
                    filesize = fmt.get('filesize_approx')
                filesize_str = f"{(filesize or 0) / (1024*1024):.1f}MB" if filesize else 'Unknown'

                # Format resolution display
                resolution_str = f"{height}p" if height else fmt.get('resolution', 'Unknown')

                # Create button with format information
                button_text = f"{resolution_str} {ext} ({filesize_str})"
                row.append(InlineKeyboardButton(
                    button_text,
                    callback_data=f"f:{format_id}:0"  # 0 = not audio only
                ))

                # Create rows with 2 buttons each
                if len(row) == 2:
                    keyboard.append(row)
                    row = []

            # Add any remaining buttons
            if row:
                keyboard.append(row)

        # Add audio formats
        if audio_formats:
            # Sort audio by quality (bitrate or filesize)
            audio_formats.sort(key=lambda x: (x.get('abr', 0) or 0, x.get('filesize', 0) or 0), reverse=True)

            # Add header for audio formats
            keyboard.append([InlineKeyboardButton("🎵 Audio Only", callback_data="h")])

            # Limit to max 4 audio formats
            selected_audio_formats = []
            seen_exts = set()
            # Try to find high quality audio in different formats
            audio_exts = set()

            # Prioritize common audio formats (mp3, m4a, etc.)
            priority_exts = ['mp3', 'm4a', 'ogg', 'opus', 'aac', 'flac', 'wav']
            for ext in priority_exts:
                matching_formats = [f for f in audio_formats if f.get('ext') == ext]
                if matching_formats:
                    # Sort by bitrate if available
                    matching_formats.sort(key=lambda x: (x.get('abr', 0) or 0), reverse=True)
                    # Take the highest quality one
                    selected_audio_formats.append(matching_formats[0])
                    seen_exts.add(ext)

            # Add other unique formats until we have 4
            for fmt in audio_formats:
                ext = fmt.get('ext', '')
                if ext not in seen_exts and len(selected_audio_formats) < 4:
                    selected_audio_formats.append(fmt)
                    seen_exts.add(ext)

            # Create buttons for audio formats (2 per row)
            row = []
            for fmt in selected_audio_formats:
                format_id = fmt.get('format_id', '')
                ext = fmt.get('ext', 'unknown')
                abr = fmt.get('abr', 0)

                # Get quality info
                quality_str = f"{int(abr)}kbps" if abr else ""
                filesize = fmt.get('filesize', 0) or 0
                filesize_str = f"{filesize / (1024*1024):.1f}MB" if filesize else 'Unknown'

                # Format button text
                button_text = f"{ext.upper()} {quality_str}".strip()
                if filesize_str != 'Unknown':
                    button_text += f" ({filesize_str})"

                row.append(InlineKeyboardButton(
                    button_text,
                    callback_data=f"f:{format_id}:1"  # 1 = audio only
                ))

                # Create rows with 2 buttons each
                if len(row) == 2:
                    keyboard.append(row)
                    row = []

            # Add any remaining buttons
            if row:
                keyboard.append(row)

        # Add a "Cancel" button at the bottom
        keyboard.append([
            InlineKeyboardButton("❌ Cancel", callback_data="c")
        ])

        # Create reply markup
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Prepare media info for display
        source_text = ""
        if 'extractor' in info:
            source = info.get('extractor', '').replace('_', ' ').title()
            source_text = f"Source: {source}\n"

        duration = info.get('duration')
        duration_text = ""
        if duration:
            minutes, seconds = divmod(int(duration), 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                duration_text = f"Duration: {hours}h {minutes}m {seconds}s\n"
            else:
                duration_text = f"Duration: {minutes}m {seconds}s\n"

        # Update status message with format selection
        await status_message.edit_text(
            f"📹 <b>{title}</b>\n\n{source_text}{duration_text}\nPlease select a format to download:",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Error preparing format options: {e}")
        await status_message.edit_text(f"An error occurred while fetching formats: {str(e)}")

async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle format selection from inline keyboard."""
    query = update.callback_query
    await query.answer()

    # Get the callback data
    data = query.data

    # Handle header buttons (no action needed)
    if data == "h":
        return

    # Parse the callback data
    parts = data.split(":", 2)

    # Handle header buttons (no action needed)
    if data.startswith("header_noop"):
        return

    # Get URL from user data
    url = context.user_data.get('current_url')

    # Handle cancellation
    if parts[0] == "c" or parts[0] == "cancel":
        await query.edit_message_text("Download canceled.")
        return

    # Handle format selection
    if parts[0] == "f" and len(parts) == 3:
        format_id = parts[1]
        is_audio_only = parts[2] == "1"  # 1 = audio only, 0 = video

        # Check if we have URL in context
        if not url:
            await query.edit_message_text("Session expired. Please send the URL again.")
            return

        # Store the selected format in user data
        context.user_data['format_id'] = format_id
        context.user_data['is_audio_only'] = is_audio_only

        # Get format description
        media_type = "audio" if is_audio_only else "video"

        # Update the message to show downloading status
        try:
            status_message = await query.edit_message_text(
                f"⏳ Starting download of selected {media_type} format, please wait...\n\n"
                f"This {media_type} will be sent when the download completes.\n"
                f"Depending on size, this may take a few moments."
            )
        except Exception as e:
            logger.error(f"Error updating message: {e}")
            # Try to send a new message instead
            status_message = await query.message.reply_text(
                f"⏳ Starting download of selected {media_type} format, please wait...\n\n"
                f"This {media_type} will be sent when the download completes.\n"
                f"Depending on size, this may take a few moments."
            )

        # Start the download process
        await download_and_send_video(update, context, url, status_message)
    elif parts[0] not in ["h", "c"]:
        await query.edit_message_text("Invalid format selection. Please try again.")

async def download_and_send_video(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, status_message: Message) -> None:
    """Common function to download and send video."""
    temp_dir = None
    output_path = None
    thread = None

    try:
        if not url:
            await status_message.edit_text("Error: No URL provided. Please try again.")
            return

        # Get video info from context if available, otherwise extract it
        info = context.user_data.get('video_info')
        if not info:
            try:
                await status_message.edit_text("Fetching video information...")
            except Exception:
                pass
            # Run synchronous yt-dlp call in a thread
            info = await asyncio.to_thread(extract_video_info, url)
            if not info:
                await status_message.edit_text("Error: Could not extract video information. Please try again with a different URL.")
                return

        # Check file size if available
        if 'filesize' in info and info['filesize'] and info['filesize'] > MAX_FILE_SIZE:
            await status_message.edit_text(
                f"Sorry, the video is too large to send via Telegram "
                f"(size: {info['filesize'] // 1000000}MB, max: {MAX_FILE_SIZE // 1000000}MB)."
            )
            return

        # Create temporary directory for download
        temp_dir = tempfile.mkdtemp()

        # Get format settings from context
        format_id = context.user_data.get('format_id')
        is_audio_only = context.user_data.get('is_audio_only', False)

        # Use appropriate file extension
        file_ext = 'mp3' if is_audio_only else 'mp4'
        temp_path = os.path.join(temp_dir, f"downloaded_media.{file_ext}")
        logger.info(f"Temporary directory created: {temp_dir}. Will download to: {temp_path}")

        # Create a thread to download the video
        download_complete = threading.Event()
        download_result = [None]  # Use a list to store the result from the thread
        download_error = [None]   # Use a list to store any exception from the thread
        progress_data = {}        # Shared dictionary to store progress information

        def download_thread():
            try:
                result = download_video(url, temp_path, progress_data, format_id, is_audio_only)
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
                            await status_message.edit_text(f"⏬ Downloading... {file_size:.2f} MB downloaded")
                    elif status == 'downloading':
                        logger.debug(f"Progress data: {progress_data}")
                        percent = progress_data.get('_percent_str', 'N/A')
                        speed = progress_data.get('_speed_str', 'N/A')
                        eta = progress_data.get('_eta_str', '')
                        filename = progress_data.get('filename', 'media')

                        message = f"⏬ Downloading {os.path.basename(filename)}...\n"
                        message += f"Progress: {percent} at {speed}\n"
                        if eta:
                            message += f"ETA: {eta}"

                        await status_message.edit_text(message)
                    elif status == 'finished':
                        await status_message.edit_text("✅ Download complete. Processing media...")

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
            await status_message.edit_text("Sorry, there was an error downloading the media.")
            return

        logger.info(f"Media downloaded to: {output_path}")

        # Check if file exists and size is within limits
        file_size = os.path.getsize(output_path)
        if file_size > MAX_FILE_SIZE:
            await status_message.edit_text(
                f"Sorry, the downloaded media is too large to send via Telegram "
                f"(size: {file_size // 1048576}MB, max: {MAX_FILE_SIZE // 1048576}MB)."
            )
            os.unlink(output_path)
            shutil.rmtree(temp_dir)
            return

        # Send video
        await status_message.edit_text("⏫ Upload in progress...")

        # Determine if this is from a callback query or direct message
        if update.callback_query:
            user_message = update.callback_query.message.reply_to_message
            chat_id = update.callback_query.message.chat_id
        else:
            user_message = update.message
            chat_id = update.message.chat_id

        # Prepare a more detailed caption
        title = info.get('title', 'Unknown')
        source_name = ""
        if 'extractor' in info:
            source_name = info.get('extractor', '').replace('_', ' ').title()

        caption = f"Title: {title}\n"
        if source_name:
            caption += f"Platform: {source_name}\n"
        caption += f"Source: {url}"

        media_type = "audio" if is_audio_only else "video"

        with open(output_path, 'rb') as media_file:
            if is_audio_only:
                # Send as audio
                if user_message:
                    await user_message.reply_audio(
                        audio=media_file,
                        caption=caption,
                        title=title,
                        performer=source_name,
                        read_timeout=120,
                        write_timeout=120
                    )
                else:
                    from telegram import Bot
                    bot = context.bot
                    await bot.send_audio(
                        chat_id=chat_id,
                        audio=media_file,
                        caption=caption,
                        title=title,
                        performer=source_name,
                        read_timeout=120,
                        write_timeout=120
                    )
            else:
                # Send as video
                if user_message:
                    await user_message.reply_video(
                        video=media_file,
                        caption=caption,
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120
                    )
                else:
                    from telegram import Bot
                    bot = context.bot
                    await bot.send_video(
                        chat_id=chat_id,
                        video=media_file,
                        caption=caption,
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120
                    )

        # Send completion message
        success_message = f"✅ Download complete! Your {media_type} has been sent."

        # Cleanup
        if output_path and os.path.exists(output_path):
            os.unlink(output_path)
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)  # Remove the temporary directory and all contents

        try:
            await status_message.edit_text(success_message)
        except Exception:
            logger.warning("Could not update status message after completion")

    except Exception as e:
        logger.error(f"Error: {e}")
        await status_message.edit_text(f"An error occurred: {str(e)}")

        # Cleanup in case of error
        try:
            # Cancel any running thread if it's still active
            if thread and thread.is_alive():
                logger.info("Waiting for download thread to finish...")
                thread.join(timeout=2)  # Give it a short time to finish

            # Clean up files
            if output_path and os.path.exists(output_path):
                os.unlink(output_path)
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup after exception: {cleanup_error}")

def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("No bot token provided. Please set TELEGRAM_BOT_TOKEN in .env file.")
        logger.error("Create a .env file with TELEGRAM_BOT_TOKEN=your_token_here")
        return

    if not ALLOWED_USERS or all(not user.strip() for user in ALLOWED_USERS):
        logger.warning("No allowed users specified. Nobody will be able to use this bot.")
        logger.warning("Add user IDs to ALLOWED_USERS in .env file (comma-separated)")

    try:
        # Create the Application and pass it your bot's token
        application = Application.builder().token(BOT_TOKEN).build()
    except Exception as e:
        logger.error(f"Failed to create application with token: {e}")
        logger.error("Please check your TELEGRAM_BOT_TOKEN in .env file")
        return

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Add message handler for URLs
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_url))

    # Add callback query handler for format selection
    application.add_handler(CallbackQueryHandler(handle_format_selection))

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

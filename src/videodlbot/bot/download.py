import os
import logging
import tempfile
import shutil
import time
import threading
import uuid
import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from ..config import settings
from ..utils import BYTES_MB
from ..utils import is_valid_url, is_supported_platform
from ..download import extract_video_info, download_video
from ..storage import upload_to_firebase
from .common import authorized, try_edit_text
from .progress import build_download_progress_message, build_pp_progress_message

logger = logging.getLogger(__name__)


class DownloadContext:
    def __init__(self, url: str, info: dict, temp_dir: str, temp_path: str):
        self.url = url
        self.info = info
        self.temp_dir = temp_dir
        self.temp_path = temp_path
        self.download_complete = threading.Event()
        self.download_result = [None]
        self.download_error = [None]
        self.progress_data = {}
        self.thread = None

    def cleanup(self):
        try:
            if self.thread and self.thread.is_alive():
                logger.info("Waiting for download thread to finish...")
                self.thread.join(timeout=2)

            if self.download_result[0] and os.path.exists(self.download_result[0]):
                os.unlink(self.download_result[0])
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")


async def _validate_url(url: str, update) -> bool:
    if not is_valid_url(url):
        await update.message.reply_text("Please provide a valid URL.")
        return False

    if not is_supported_platform(url):
        await update.message.reply_text(
            "Sorry, this URL is not from a supported platform.\n"
            "I can download videos from YouTube, Instagram, and Twitter/X."
        )
        return False
    return True


async def _check_file_size(info: dict, status_message) -> bool:
    if 'filesize' in info and info['filesize'] and info['filesize'] > settings.MAX_FILE_SIZE:
        await try_edit_text(status_message,
            f"Sorry, the video is too large"
            f"(size: {info['filesize'] // BYTES_MB}MB, max: {settings.MAX_FILE_SIZE // BYTES_MB}MB supported)."
        )
        return False
    return True


def _create_download_thread(ctx: DownloadContext):
    def download_thread():
        try:
            result = download_video(ctx.url, ctx.info, ctx.temp_path, ctx.progress_data)
            ctx.download_result[0] = result # pyright: ignore
        except Exception as e:
            logger.error(f"Error in download thread: {e}")
            ctx.download_error[0] = e # pyright: ignore
        finally:
            logger.info("Download thread completed")
            ctx.download_complete.set()

    ctx.thread = threading.Thread(target=download_thread) #pyright: ignore
    if ctx.thread is None:
        raise RuntimeError("Failed to create download thread")
    ctx.thread.daemon = True
    ctx.thread.start()


async def _monitor_download_progress(ctx: DownloadContext, status_message):
    prev_message = ''
    last_update_time = 0

    while not ctx.download_complete.is_set():
        current_time = time.time()
        if current_time - last_update_time >= 1.5:
            last_update_time = current_time
            message = _build_progress_message(ctx)

            if prev_message != message and message:
                await try_edit_text(status_message, message)
                prev_message = message

        await asyncio.sleep(0.5)


def _build_progress_message(ctx: DownloadContext) -> str:
    if 'download_progress' in ctx.progress_data:
        dl_progress_data = ctx.progress_data.get('download_progress', {})
        status = dl_progress_data.get('status', '')

        if not dl_progress_data and os.path.exists(ctx.temp_path):
            file_size = os.path.getsize(ctx.temp_path) / (1024 * 1024)
            return f"Downloading... {file_size or 0:.2f} MB downloaded"
        elif status == 'downloading':
            logger.debug(f"Progress data: {dl_progress_data}")
            return build_download_progress_message(dl_progress_data)
        elif status == 'finished':
            return "Download complete. Processing video..."
    elif 'postprocess_progress' in ctx.progress_data:
        pp_progress_data = ctx.progress_data.get('postprocess_progress', {})
        return build_pp_progress_message(pp_progress_data)
    return ''


async def _handle_large_file(output_path: str, info: dict, url: str, update, status_message) -> bool:
    file_size = os.path.getsize(output_path)
    if file_size <= settings.MAX_TELEGRAM_FILE_SIZE:
        return False

    await status_message.edit_text("File too large for Telegram. Uploading to cloud storage...")

    title = info.get('title', 'video')
    unique_filename = f"{uuid.uuid4()}_{title.replace(' ', '_')}.mp4"
    download_url = upload_to_firebase(output_path, unique_filename, title=title)

    if download_url:
        caption = (f"Title: {title}\n"
                  f"Size: {file_size // BYTES_MB}MB (too large for Telegram)\n"
                  f"Download: {download_url}\n"
                  f"Source: {url}")
        await update.message.reply_text(caption)
    else:
        await status_message.edit_text(
            f"Sorry, failed to upload the video to cloud storage. "
            f"The video is {file_size // BYTES_MB}MB which exceeds Telegram's {settings.MAX_TELEGRAM_FILE_SIZE // BYTES_MB}MB limit."
        )
    return True


async def _send_video_to_telegram(output_path: str, info: dict, url: str, update, status_message):
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


@authorized
async def process_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context # Unused parameter
    if update.message is None or not update.message.text:
        return

    url = update.message.text.strip()

    if not await _validate_url(url, update):
        logger.warning(f"[Process URL] Invalid or unsupported URL received: {url}")
        return

    status_message = await update.message.reply_text("Downloading video, please wait...")
    ctx = None

    try:
        info = extract_video_info(url)

        if not await _check_file_size(info, status_message):
            return

        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, "video.mp4")
        logger.info(f"Temporary directory created: {temp_dir}. Will download to: {temp_path}")

        ctx = DownloadContext(url, info, temp_dir, temp_path)
        _create_download_thread(ctx)

        try:
            await _monitor_download_progress(ctx, status_message)
        except asyncio.CancelledError:
            logger.warning("Download status updates were cancelled")
            raise
        except Exception as e:
            logger.error(f"Error while updating status: {e}")

        if ctx.thread is not None and ctx.thread.is_alive():
            ctx.thread.join(timeout=5)

        if ctx.download_error[0]:
            raise ctx.download_error[0]

        output_path = ctx.download_result[0]

        if not output_path or not os.path.exists(output_path):
            await try_edit_text(status_message, "Sorry, there was an error downloading the video.")
            return

        logger.info(f"Video downloaded to: {output_path}")

        if await _handle_large_file(output_path, info, url, update, status_message):
            ctx.cleanup()
            await status_message.delete()
            return

        await _send_video_to_telegram(output_path, info, url, update, status_message)
        ctx.cleanup()
        await status_message.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await try_edit_text(status_message, f"An error occurred: {str(e)}")
        if ctx:
            ctx.cleanup()

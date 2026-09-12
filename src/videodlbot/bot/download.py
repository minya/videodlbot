import os
import logging
import tempfile
import shutil
import time
import threading
import uuid
import asyncio
from contextlib import ExitStack
from typing import Any, final
from telegram import InputMediaPhoto, InputMediaVideo, Message, Update
from telegram.ext import ContextTypes

from ..config import settings
from ..utils import BYTES_MB
from ..utils import is_valid_url, is_supported_platform
from ..download import extract_video_info, download_video
from ..download import DownloadedMedia, InstagramPost, download_instagram_media, fetch_instagram_post, is_instagram_post_url
from ..storage import upload_to_firebase
from .common import authorized, try_edit_text
from .progress import build_download_progress_message, build_pp_progress_message

logger = logging.getLogger(__name__)

MEDIA_GROUP_MAX_ITEMS = 10
CAPTION_MAX_LENGTH = 1024


@final
class DownloadContext:
    def __init__(self, url: str, info: dict[str, Any], temp_dir: str, temp_path: str):
        self.url = url
        self.info = info
        self.temp_dir = temp_dir
        self.temp_path = temp_path
        self.download_complete = threading.Event()
        self.download_result: list[str | None] = [None]
        self.download_error: list[BaseException | None] = [None]
        self.progress_data: dict[str, Any] = {}
        self.thread: threading.Thread | None = None

    def cleanup(self) -> None:
        try:
            if self.thread and self.thread.is_alive():
                logger.info("Waiting for download thread to finish...")
                self.thread.join(timeout=2)

            result = self.download_result[0]
            if result and os.path.exists(result):
                os.unlink(result)
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")


async def _validate_url(url: str, update: Update) -> bool:
    if not update.message:
        return False
    if not is_valid_url(url):
        _ = await update.message.reply_text("Please provide a valid URL.")
        return False

    if not is_supported_platform(url):
        _ = await update.message.reply_text(
            "Sorry, this URL is not from a supported platform.\n"
            "I can download videos from YouTube, Instagram, and Twitter/X, "
            "and photos or carousels from Instagram."
        )
        return False
    return True


async def _check_file_size(info: dict[str, Any], status_message: Message) -> bool:
    if 'filesize' in info and info['filesize'] and info['filesize'] > settings.MAX_FILE_SIZE:
        await try_edit_text(status_message,
            f"Sorry, the video is too large"
            f"(size: {info['filesize'] // BYTES_MB}MB, max: {settings.MAX_FILE_SIZE // BYTES_MB}MB supported)."
        )
        return False
    return True


def _create_download_thread(ctx: DownloadContext) -> None:
    def download_thread() -> None:
        try:
            result = download_video(ctx.url, ctx.info, ctx.temp_path, ctx.progress_data)
            ctx.download_result[0] = result
        except Exception as e:
            logger.error(f"Error in download thread: {e}")
            ctx.download_error[0] = e
        finally:
            logger.info("Download thread completed")
            ctx.download_complete.set()

    ctx.thread = threading.Thread(target=download_thread)
    ctx.thread.daemon = True
    ctx.thread.start()


async def _monitor_download_progress(ctx: DownloadContext, status_message: Message) -> None:
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
        dl_progress_data: dict[str, Any] = ctx.progress_data.get('download_progress', {})
        status: str = dl_progress_data.get('status', '')

        if not dl_progress_data and os.path.exists(ctx.temp_path):
            file_size = os.path.getsize(ctx.temp_path) / (1024 * 1024)
            return f"Downloading... {file_size or 0:.2f} MB downloaded"
        elif status == 'downloading':
            logger.debug(f"Progress data: {dl_progress_data}")
            return build_download_progress_message(dl_progress_data)
        elif status == 'finished':
            return "Download complete. Processing video..."
    elif 'postprocess_progress' in ctx.progress_data:
        pp_progress_data: dict[str, Any] = ctx.progress_data.get('postprocess_progress', {})
        return build_pp_progress_message(pp_progress_data)
    return ''


async def _handle_large_file(output_path: str, info: dict[str, Any], url: str, update: Update, status_message: Message) -> bool:
    file_size = os.path.getsize(output_path)
    if file_size <= settings.MAX_TELEGRAM_FILE_SIZE:
        return False

    await try_edit_text(status_message, "File too large for Telegram. Uploading to cloud storage...")

    title = info.get('title', 'video')
    unique_filename = f"{uuid.uuid4()}_{title.replace(' ', '_')}.mp4"
    user_id = str(update.effective_user.id) if update.effective_user else None
    download_url = upload_to_firebase(output_path, unique_filename, title=title, user_id=user_id)

    if download_url and update.message:
        caption = (f"Title: {title}\n"
                  f"Size: {file_size // BYTES_MB}MB (too large for Telegram)\n"
                  f"Download: {download_url}\n"
                  f"Source: {url}")
        _ = await update.message.reply_text(caption)
    else:
        await try_edit_text(
            status_message,
            f"Sorry, failed to upload the video to cloud storage. "
            f"The video is {file_size // BYTES_MB}MB which exceeds Telegram's {settings.MAX_TELEGRAM_FILE_SIZE // BYTES_MB}MB limit.",
        )
    return True


async def _send_video_to_telegram(output_path: str, info: dict[str, Any], url: str, update: Update, status_message: Message) -> None:
    if not update.message:
        return
    await try_edit_text(status_message, "Upload in progress...")

    caption = f"Title: {info.get('title', 'Unknown')}\nSource: {url}"
    width = info.get('width', None)
    height = info.get('height', None)

    with open(output_path, 'rb') as video_file:
        _ = await update.message.reply_video(
            video=video_file,
            caption=caption,
            width=width,
            height=height,
            supports_streaming=True,
            read_timeout=120,
            write_timeout=120
        )


def _build_post_caption(post: InstagramPost, url: str) -> str:
    source = f"Source: {url}"
    if not post.caption:
        return source
    caption = post.caption.strip()
    limit = CAPTION_MAX_LENGTH - len(source) - 2
    if len(caption) > limit:
        caption = caption[:limit - 3].rstrip() + '...'
    return f"{caption}\n\n{source}"


def _build_input_media(
    item: DownloadedMedia,
    stack: ExitStack,
    caption: str | None,
) -> InputMediaPhoto | InputMediaVideo | None:
    if item.media.kind == 'video':
        if item.size > settings.MAX_TELEGRAM_FILE_SIZE:
            return None
        return InputMediaVideo(
            media=stack.enter_context(open(item.path, 'rb')),
            caption=caption,
            width=item.media.width,
            height=item.media.height,
            supports_streaming=True,
        )
    if item.size > settings.MAX_TELEGRAM_PHOTO_SIZE:
        return None
    return InputMediaPhoto(media=stack.enter_context(open(item.path, 'rb')), caption=caption)


async def _send_instagram_media(
    downloaded: list[DownloadedMedia],
    post: InstagramPost,
    url: str,
    update: Update,
    status_message: Message,
) -> int:
    """Send downloaded items as photos/videos in groups of up to 10. Returns the number of skipped items."""
    if not update.message:
        return 0
    await try_edit_text(status_message, "Upload in progress...")

    caption: str | None = _build_post_caption(post, url)
    skipped = 0
    sendable = [item for item in downloaded if item.size <= settings.MAX_TELEGRAM_FILE_SIZE]

    for start in range(0, len(sendable), MEDIA_GROUP_MAX_ITEMS):
        chunk = sendable[start:start + MEDIA_GROUP_MAX_ITEMS]
        with ExitStack() as stack:
            media_group: list[InputMediaPhoto | InputMediaVideo] = []
            for item in chunk:
                input_media = _build_input_media(item, stack, caption if not media_group else None)
                if input_media is None:
                    skipped += 1
                    continue
                media_group.append(input_media)
            if not media_group:
                continue
            caption = None

            if len(media_group) == 1:
                single = media_group[0]
                if isinstance(single, InputMediaVideo):
                    _ = await update.message.reply_video(
                        video=single.media, caption=single.caption, width=single.width, height=single.height,
                        supports_streaming=True, read_timeout=120, write_timeout=120,
                    )
                else:
                    _ = await update.message.reply_photo(
                        photo=single.media, caption=single.caption, read_timeout=120, write_timeout=120,
                    )
            else:
                _ = await update.message.reply_media_group(
                    media=media_group, read_timeout=120, write_timeout=120,
                )

    return skipped + (len(downloaded) - len(sendable))


async def _process_instagram_post(post: InstagramPost, url: str, update: Update, status_message: Message) -> None:
    if not post.items:
        await try_edit_text(status_message, "Sorry, this Instagram post contains no downloadable media.")
        return

    total = len(post.items)
    temp_dir = tempfile.mkdtemp()
    logger.info(f"Temporary directory created: {temp_dir}. Downloading {total} Instagram items")
    progress = {'done': 0}

    def on_item_done(done: int, _total: int) -> None:
        progress['done'] = done

    try:
        task = asyncio.create_task(asyncio.to_thread(download_instagram_media, post, temp_dir, on_item_done))
        prev_message = ''
        while not task.done():
            message = f"Downloading Instagram post... {progress['done']}/{total} items"
            if message != prev_message:
                await try_edit_text(status_message, message)
                prev_message = message
            await asyncio.sleep(1.5)
        downloaded = task.result()

        if not downloaded:
            await try_edit_text(status_message, "Sorry, there was an error downloading the Instagram post.")
            return

        skipped = await _send_instagram_media(downloaded, post, url, update, status_message)
        failed = total - len(downloaded)
        if failed or skipped:
            notes: list[str] = []
            if failed:
                notes.append(f"{failed} item(s) failed to download")
            if skipped:
                notes.append(f"{skipped} item(s) were too large for Telegram")
            await try_edit_text(status_message, "Sent with issues: " + ", ".join(notes) + ".")
        else:
            _ = await status_message.delete()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@authorized
async def process_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context # Unused parameter
    if update.message is None or not update.message.text:
        return

    url = update.message.text.strip()

    if not await _validate_url(url, update):
        logger.warning(f"[Process URL] Invalid or unsupported URL received: {url}")
        return

    status_message = await update.message.reply_text("Downloading, please wait...")
    ctx = None

    try:
        if is_instagram_post_url(url):
            post = await asyncio.to_thread(fetch_instagram_post, url)
            if post and (post.is_carousel or post.has_images):
                await _process_instagram_post(post, url, update, status_message)
                return

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
            _ = await status_message.delete()
            return

        await _send_video_to_telegram(output_path, info, url, update, status_message)
        ctx.cleanup()
        _ = await status_message.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await try_edit_text(status_message, f"An error occurred: {str(e)}")
        if ctx:
            ctx.cleanup()

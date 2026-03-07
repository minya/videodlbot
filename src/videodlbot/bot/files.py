import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..config import settings
from ..storage import delete_firebase_file, list_firebase_files
from ..utils import BYTES_MB
from .common import authorized, try_edit_text

logger = logging.getLogger(__name__)


@authorized
async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /listfiles command to show all files in Firebase storage."""
    del context  # Unused parameter

    if update.message is None:
        return

    user_id = str(update.effective_user.id) if update.effective_user else None
    is_admin = user_id in settings.ADMIN_USERS if user_id else False

    status_message = await update.message.reply_text("Loading files from storage...")

    try:
        files = list_firebase_files(user_id=user_id, is_admin=is_admin)

        if files is None:
            await try_edit_text(status_message, "Firebase storage is not configured or an error occurred.")
            return

        if not files:
            await try_edit_text(status_message, "No files found in storage.")
            return

        # Sort files by creation date (newest first)
        files.sort(key=lambda x: x["created"] or datetime.min, reverse=True)

        # Build message with file list
        header = "All files in storage:\n" if is_admin else "Your files in storage:\n"
        message_parts = [header]
        keyboard = []

        for idx, file in enumerate(files[:20]):  # Limit to 20 most recent files
            size_mb = file["size"] / BYTES_MB
            created = file["created"]
            created_date = created.strftime("%Y-%m-%d %H:%M") if created else "N/A"
            title = file["title"]

            url = file["url"]
            owner_info = ""
            if is_admin and file.get("user_id"):
                owner_info = f"   Owner: {file['user_id']}\n"
            message_parts.append(
                f"\n{idx + 1}. {title}\n"
                f"   Size: {size_mb:.2f} MB | Created: {created_date}\n"
                f"{owner_info}"
                f"   {url}"
            )

            # Add delete button for each file (using index)
            keyboard.append(
                [InlineKeyboardButton(f"Delete #{idx + 1}", callback_data=f"del:{idx}")]
            )

        if len(files) > 20:
            message_parts.append(f"\n\n(Showing 20 of {len(files)} files)")

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await try_edit_text(status_message, "".join(message_parts), reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        await try_edit_text(status_message, f"An error occurred: {str(e)}")


@authorized
async def delete_file_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle delete button callback from inline keyboard."""
    del context  # Unused parameter
    query = update.callback_query
    if query is None or query.data is None:
        return

    _ = await query.answer()

    user_id = str(update.effective_user.id) if update.effective_user else None
    is_admin = user_id in settings.ADMIN_USERS if user_id else False

    try:
        # Parse callback data to get file index
        _, idx_str = query.data.split(":", 1)
        file_idx = int(idx_str)

        # Fetch current file list (same filter as list command)
        files = list_firebase_files(user_id=user_id, is_admin=is_admin)
        if not files:
            await try_edit_text(query, "No files found in storage.")
            return

        # Sort files by creation date (same as list command)
        files.sort(key=lambda x: x["created"] or datetime.min, reverse=True)

        # Check if index is valid
        if file_idx < 0 or file_idx >= len(files):
            await try_edit_text(query, "File no longer exists or list has changed. Use /listfiles to refresh.")
            return

        # Get the file to delete
        file_to_delete = files[file_idx]
        filename = file_to_delete["name"]
        title = file_to_delete["title"]

        # Delete the file
        success = delete_firebase_file(filename)

        if success:
            await try_edit_text(
                query,
                f"File deleted successfully: {title}\n\n"
                "Use /listfiles to see updated list.",
            )
        else:
            await try_edit_text(
                query,
                f"Failed to delete file: {title}\n\n"
                "The file may not exist or an error occurred.",
            )

    except ValueError:
        await try_edit_text(query, "Invalid file selection.")
    except Exception as e:
        logger.error(f"Error in delete callback: {e}")
        await try_edit_text(query, f"An error occurred: {str(e)}")

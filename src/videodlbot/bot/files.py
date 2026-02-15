import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..utils import BYTES_MB
from ..storage import list_firebase_files, delete_firebase_file
from .common import authorized

logger = logging.getLogger(__name__)


@authorized
async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /listfiles command to show all files in Firebase storage."""
    del context # Unused parameter

    if update.message is None:
        return

    status_message = await update.message.reply_text("Loading files from storage...")

    try:
        files = list_firebase_files()

        if files is None:
            await status_message.edit_text("Firebase storage is not configured or an error occurred.")
            return

        if not files:
            await status_message.edit_text("No files found in storage.")
            return

        # Sort files by creation date (newest first)
        files.sort(key=lambda x: x['created'], reverse=True)

        # Build message with file list
        message_parts = ["Files in storage:\n"]
        keyboard = []

        for idx, file in enumerate(files[:20]):  # Limit to 20 most recent files
            size_mb = file['size'] / BYTES_MB
            created_date = file['created'].strftime('%Y-%m-%d %H:%M')
            title = file['title']

            url = file['url']
            message_parts.append(
                f"\n{idx + 1}. {title}\n"
                f"   Size: {size_mb:.2f} MB | Created: {created_date}\n"
                f"   {url}"
            )

            # Add delete button for each file (using index)
            keyboard.append([
                InlineKeyboardButton(
                    f"Delete #{idx + 1}",
                    callback_data=f"del:{idx}"
                )
            ])

        if len(files) > 20:
            message_parts.append(f"\n\n(Showing 20 of {len(files)} files)")

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await status_message.edit_text(
            ''.join(message_parts),
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        await status_message.edit_text(f"An error occurred: {str(e)}")


@authorized
async def delete_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle delete button callback from inline keyboard."""
    del context # Unused parameter
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    try:
        # Parse callback data to get file index
        _, idx_str = query.data.split(':', 1)
        file_idx = int(idx_str)

        # Fetch current file list
        files = list_firebase_files()
        if not files:
            await query.edit_message_text("No files found in storage.")
            return

        # Sort files by creation date (same as list command)
        files.sort(key=lambda x: x['created'], reverse=True)

        # Check if index is valid
        if file_idx < 0 or file_idx >= len(files):
            await query.edit_message_text("File no longer exists or list has changed. Use /listfiles to refresh.")
            return

        # Get the file to delete
        file_to_delete = files[file_idx]
        filename = file_to_delete['name']
        title = file_to_delete['title']

        # Delete the file
        success = delete_firebase_file(filename)

        if success:
            await query.edit_message_text(
                f"File deleted successfully: {title}\n\n"
                "Use /listfiles to see updated list."
            )
        else:
            await query.edit_message_text(
                f"Failed to delete file: {title}\n\n"
                "The file may not exist or an error occurred."
            )

    except ValueError:
        await query.edit_message_text("Invalid file selection.")
    except Exception as e:
        logger.error(f"Error in delete callback: {e}")
        await query.edit_message_text(f"An error occurred: {str(e)}")

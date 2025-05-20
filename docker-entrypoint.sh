#!/bin/bash
set -e

# Print welcome message
echo "Starting Video Downloader Telegram Bot in Docker container"

# Check if the token is set
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN environment variable is not set."
    echo "Please set it by passing -e TELEGRAM_BOT_TOKEN=your_token to docker run,"
    echo "or by setting it in your docker-compose.yml file."
    exit 1
fi

# Create downloads directory if it doesn't exist
mkdir -p /app/downloads

# Check if cookies.txt exists and print appropriate message
if [ -f /app/cookies.txt ]; then
    echo "Found cookies.txt file, will use for authentication if USE_COOKIES=true"
else
    echo "No cookies.txt file found. If you need authentication for certain sites,"
    echo "place a cookies.txt file in the bot directory."
fi

# Display configuration
echo "Configuration:"
echo "- Debug mode: $DEBUG_MODE"
echo "- Max file size: $MAX_FILE_SIZE bytes"
echo "- Download timeout: ${DOWNLOAD_TIMEOUT:-30} seconds"
echo "- Download retries: ${DOWNLOAD_RETRIES:-3}"
echo "- Use cookies: ${USE_COOKIES:-false}"
echo "- Preferred format: ${PREFERRED_FORMAT:-mp4}"

# Execute CMD
echo "Starting bot..."
exec "$@"
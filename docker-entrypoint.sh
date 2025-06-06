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

# Execute CMD
echo "Starting bot..."
exec "$@"
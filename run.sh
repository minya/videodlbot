#!/bin/bash
# Script to run the Video Downloader Telegram Bot

# Ensure we're in the right directory
cd "$(dirname "$0")"

# Remove existing virtual environment if it exists
if [ -d "venv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf venv
fi

# Create fresh virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Installing/updating dependencies..."
pip install -r requirements.txt

# Check if .env file exists, create template if not
if [ ! -f ".env" ]; then
    echo "Creating .env template file..."
    echo "# Telegram Bot Configuration" > .env
    echo "TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here" >> .env
    echo "" >> .env
    echo "# Optional Configuration" >> .env
    echo "# MAX_FILE_SIZE=52428800  # Default: 50MB" >> .env
    
    echo "Please edit the .env file to add your Telegram Bot Token."
    exit 1
fi

# Check if token is set
if grep -q "your_telegram_bot_token_here" .env; then
    echo "ERROR: Please edit the .env file to add your Telegram Bot Token."
    exit 1
fi

# Run the bot
echo "Starting Video Downloader Telegram Bot..."
python main.py

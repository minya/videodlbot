# Video Downloader Telegram Bot

A Telegram bot that can download videos from YouTube, Instagram, and Twitter/X using yt-dlp.

## Features

- Downloads videos from YouTube, Instagram, and Twitter/X
- Automatically handles different video formats
- Respects Telegram's file size limitations
- Easy to set up and deploy

## Prerequisites

- Python 3.7+
- A Telegram Bot Token (obtained from BotFather)
- yt-dlp and other dependencies

## Installation

1. Clone this repository:
   ```
   git clone <repository-url>
   cd videodlbot
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up your environment variables by editing the `.env` file:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   MAX_FILE_SIZE=50000000  # Optional: Max file size in bytes (default: 50MB)
   ```

## How to Obtain a Telegram Bot Token

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Start a chat with BotFather and use the `/newbot` command
3. Follow the instructions to create a new bot
4. Once created, BotFather will provide you with a token - copy this into your `.env` file

## Running the Bot

Start the bot with:
```
python main.py
```

The bot will run until you terminate the process (Ctrl+C).

## Using the Bot

1. Start a chat with your bot on Telegram
2. Send a URL from YouTube, Instagram, or Twitter/X
3. The bot will download the video and send it back to you

## Commands

- `/start` - Introduces the bot and explains its functionality
- `/help` - Shows usage instructions

## Limitations

- Due to Telegram API limitations, videos larger than 50MB cannot be sent
- Some websites may implement anti-scraping measures that could prevent downloads

## Deployment

For 24/7 operation, consider deploying the bot on a cloud platform or a VPS.

## Troubleshooting

- If you encounter SSL or network errors, ensure your server has the latest CA certificates
- If videos fail to download, check if yt-dlp needs to be updated: `pip install -U yt-dlp`

## License

This project is licensed under the MIT License - see the LICENSE file for details.
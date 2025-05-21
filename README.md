# Video Downloader Telegram Bot

A Telegram bot that can download videos from YouTube, Instagram, and Twitter/X using yt-dlp.

## Features

- Downloads videos from YouTube, Instagram, and Twitter/X
- Automatically handles different video formats
- Respects Telegram's file size limitations
- User access control with allowlist
- Easy to set up and deploy
- Can be run as a Docker container

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
   ALLOWED_USERS=your_telegram_user_id_here  # Comma-separated list of allowed user IDs
   MAX_FILE_SIZE=52428800  # Optional: Max file size in bytes (default: 50MB)
   ```

## How to Obtain a Telegram Bot Token and User ID

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Start a chat with BotFather and use the `/newbot` command
3. Follow the instructions to create a new bot
4. Once created, BotFather will provide you with a token - copy this into your `.env` file

To find your Telegram User ID:
1. Start a chat with [@userinfobot](https://t.me/userinfobot)
2. The bot will reply with your user ID
3. Copy this ID into the `ALLOWED_USERS` field in your `.env` file
4. For multiple users, separate IDs with commas (e.g., `123456789,987654321`)

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

Note: Only users whose Telegram IDs are listed in the `ALLOWED_USERS` setting will be able to use the bot. This helps prevent unauthorized usage.

## Commands

- `/start` - Introduces the bot and explains its functionality
- `/help` - Shows usage instructions

## Limitations

- Due to Telegram API limitations, videos larger than 50MB cannot be sent
- Some websites may implement anti-scraping measures that could prevent downloads
- Access is restricted to users specified in the `ALLOWED_USERS` setting for security

## Deployment

For 24/7 operation, consider deploying the bot on a cloud platform or a VPS.

### Running with Docker

You can easily run this bot as a Docker container. We provide both a Docker Compose setup and a convenience script for managing the Docker container.

#### Using the Helper Script

The easiest way to run the bot in Docker is with the included helper script:

1. Make the script executable:
   ```
   chmod +x docker-run.sh
   ```

2. Copy the environment file:
   ```
   cp .env.docker.sample .env
   ```

3. Edit the `.env` file to add your Telegram Bot Token, your Telegram User ID in the `ALLOWED_USERS` setting, and adjust any other settings.

4. Run the bot:
   ```
   ./docker-run.sh start
   ```

5. View logs:
   ```
   ./docker-run.sh logs
   ```

6. Stop the bot:
   ```
   ./docker-run.sh stop
   ```

7. Show all available commands:
   ```
   ./docker-run.sh help
   ```

#### Using Docker Compose Directly

If you prefer to use Docker Compose commands directly:

1. Copy the environment file:
   ```
   cp .env.docker.sample .env
   ```

2. Edit the `.env` file to add your Telegram Bot Token and User ID.

3. Build and start the container:
   ```
   docker-compose up -d
   ```

4. Stop the container:
   ```
   docker-compose down
   ```

5. View logs:
   ```
   docker-compose logs -f
   ```

#### Manual Docker Setup

If you prefer to use Docker without docker-compose:

1. Build the Docker image:
   ```
   docker build -t videodlbot .
   ```

2. Run the container:
   ```
   docker run -d --name videodlbot \
     -e TELEGRAM_BOT_TOKEN=your_token_here \
     -e ALLOWED_USERS=your_user_id_here \
     -e MAX_FILE_SIZE=1073741824 \
     -e DEBUG_MODE=false \
     -v $(pwd)/downloads:/app/downloads \
     -v $(pwd)/cookies.txt:/app/cookies.txt:ro \
     videodlbot
   ```

#### Docker Volume and Cookies

The Docker setup uses a volume for downloads to persist downloaded files between container restarts. If you need to use cookies for authentication with certain sites:

1. Create a `cookies.txt` file in the project directory.
2. Set `USE_COOKIES=true` in your `.env` file.

The cookies file will be mounted as read-only inside the container.

## Troubleshooting

- If you encounter SSL or network errors, ensure your server has the latest CA certificates
- If videos fail to download, check if yt-dlp needs to be updated: `pip install -U yt-dlp`

## License

This project is licensed under the MIT License - see the LICENSE file for details.

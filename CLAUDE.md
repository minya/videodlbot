# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Coding Preferences

**IMPORTANT: Never use emojis in code, comments, messages, or any output. User preference is text-only.**

## Project Overview

This is a Python-based Telegram bot that downloads videos from YouTube, Instagram, Twitter/X, and other platforms supported by yt-dlp. The bot features user access control, Firebase cloud storage integration for large files, and real-time download progress updates.

## Common Commands

### Running the Bot
```bash
# Local development
python main.py

# Docker (recommended for production)
./docker-run.sh start
./docker-run.sh logs
./docker-run.sh stop

# Docker Compose directly
docker-compose up -d
docker-compose logs -f
docker-compose down
```

### Testing
```bash
# Test a specific download
python test_download.py
```

### Dependencies
```bash
pip install -r requirements.txt
```

## Architecture

### Core Components

**Entry Point (`main.py`)**
- Initializes the Telegram bot application
- Sets up logging based on DEBUG_MODE
- Registers command and message handlers
- Initializes Firebase if credentials are configured
- Starts the bot's polling loop

**Configuration (`src/videodlbot/config/settings.py`)**
- Loads environment variables from `.env` file
- Key settings:
  - `BOT_TOKEN`: Telegram bot token (required)
  - `ALLOWED_USERS`: Comma-separated list of authorized Telegram user IDs
  - `MAX_FILE_SIZE`: Maximum download size in MB (default: 500 MB)
  - `MAX_TELEGRAM_FILE_SIZE`: Hard limit for Telegram uploads (50 MB)
  - `DEBUG_MODE`: Enable verbose logging
  - `COOKIE_FILE`: Auto-detected at `.secrets/cookies.txt` if exists
  - `FIREBASE_CREDENTIALS_PATH` and `FIREBASE_STORAGE_BUCKET`: For cloud storage

**Bot Handlers (`src/videodlbot/bot/handlers.py`)**
- Main message processing logic using async/await
- User authorization checks against ALLOWED_USERS
- URL validation and platform support checking
- Download orchestration using threading (synchronous yt-dlp in background thread)
- Real-time progress monitoring with message updates every 1.5 seconds
- Automatic fallback to Firebase for files exceeding Telegram's 50 MB limit
- Cleanup of temporary files via `DownloadContext.cleanup()`

**Download Logic (`src/videodlbot/download/downloader.py`)**
- `extract_video_info()`: Gets video metadata without downloading
- `download_video()`: Handles actual download with progress hooks
- Smart codec conversion: Only converts YouTube videos with incompatible codecs (not h264/h265/avc1/av01 for video, not aac/mp4a for audio)
- Uses FFmpeg for format conversion and merging when needed
- Format selection: `best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best/bestvideo+bestaudio`
- Forces IPv6 connections (`force_ipv6: True`)

**Storage (`src/videodlbot/storage/firebase.py`)**
- Optional Firebase Storage integration for large files
- `initialize_firebase()`: Called at startup if credentials exist
- `upload_to_firebase()`: Uploads file and returns public download URL
- Files uploaded to `videos/{filename}` path with public access

**Progress Tracking (`src/videodlbot/bot/progress.py`)**
- Formats download progress messages (percentage, speed, ETA)
- Formats post-processing progress messages
- Used by the async progress monitoring loop

**URL Validation (`src/videodlbot/utils/validators.py`)**
- `is_valid_url()`: Basic URL format validation
- `is_supported_platform()`: Checks if yt-dlp has an extractor for the URL

### Threading Model

The bot uses a hybrid async/threading approach:
- Main bot logic is async (Telegram handlers)
- yt-dlp downloads run in daemon threads (synchronous library)
- Progress data shared via dictionary between threads
- `DownloadContext` manages thread lifecycle and cleanup
- Main thread monitors progress with `asyncio.sleep()` while download thread runs

### File Size Handling Strategy

1. Pre-download check: Reject if metadata shows size > MAX_FILE_SIZE
2. Post-download check:
   - If ≤ 50 MB: Send directly via Telegram
   - If > 50 MB and ≤ MAX_FILE_SIZE: Upload to Firebase and provide download link
   - If > MAX_FILE_SIZE: Rejected during pre-download check

### Environment Configuration

Create `.env` file with:
```
TELEGRAM_BOT_TOKEN=your_token
ALLOWED_USERS=123456789,987654321
MAX_FILE_SIZE=500
DEBUG_MODE=false
FIREBASE_CREDENTIALS_PATH=.secrets/videodl-bot-firebase-adminsdk-xxx.json
FIREBASE_STORAGE_BUCKET=your-bucket.appspot.com
```

### Secrets Management

- `.secrets/` directory (gitignored) contains:
  - `cookies.txt`: Optional yt-dlp cookies for authenticated downloads
  - Firebase admin SDK credentials JSON
- Cookie file auto-detected by settings if present at `.secrets/cookies.txt`

### Docker Deployment

- Base image: `python:3.10-slim`
- System dependency: ffmpeg (required for video processing)
- Entry point: `docker-entrypoint.sh` (handles initialization)
- Logs limited to 5MB × 3 files via docker-compose
- No persistent volumes for downloads (temporary files cleaned up after send)

### Important Behavioral Notes

- User IDs are checked as strings, not integers
- Temporary directories created per download, cleaned up after completion or error
- Progress messages throttled to 1.5 second intervals to avoid Telegram rate limits
- Download thread is daemon and will be killed if main thread exits
- Message edits wrapped in try/except to handle Telegram API errors gracefully
- IPv6 is forced for all yt-dlp connections

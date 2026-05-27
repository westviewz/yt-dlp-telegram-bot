# yt-dlp Telegram Bot

A lightweight Telegram bot that uses `yt-dlp` to download videos and send them directly to chats.

## Features
- **Auto-deciphering**: Inherits the robust signature-deciphering capabilities of `yt-dlp`.
- **Under 50MB Auto-Filtering**: Specifically targets formats below 50MB to comply with the standard Telegram Bot API file size limits.
- **Streaming Support**: Videos are uploaded with `supports_streaming=True` enabling fast playback directly in the app.
- **Auto-clean**: Uses temporary directories to download and immediately purge raw files from the host server.

## Installation

1. Clone the repository (once pushed to GitHub).
2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Set your Telegram bot token as an environment variable:

- **Linux / macOS**:
  ```bash
  export TELEGRAM_BOT_TOKEN="your_actual_bot_token"
  ```
- **Windows (CMD)**:
  ```cmd
  set TELEGRAM_BOT_TOKEN=your_actual_bot_token
  ```
- **Windows (PowerShell)**:
  ```powershell
  $env:TELEGRAM_BOT_TOKEN="your_actual_bot_token"
  ```

Alternatively, you can edit `bot.py` and replace `YOUR_TELEGRAM_BOT_TOKEN` with your token directly (make sure not to commit your actual token!).

## Usage

Simply run:
```bash
python bot.py
```

In Telegram, start a chat with your bot using `/start`, send it any video URL (YouTube, TikTok, Twitter, Instagram, etc.), and wait for the video to be delivered!

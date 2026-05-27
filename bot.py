import os
import tempfile
import base64
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# Replace with your actual Telegram Bot Token from @BotFather
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a greeting message when the /start command is issued."""
    await update.message.reply_text(
        "👋 **Hello!** I am a premium Video Downloader Bot.\n\n"
        "Send me any video link (YouTube, TikTok, Twitter, etc.), and I'll let you choose the quality!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming text messages (URLs) and shows quality selection buttons."""
    url = update.message.text.strip()
    
    if not url.startswith('http'):
        await update.message.reply_text("❌ Please send a valid URL starting with http/https.")
        return

    # Store the URL in user_data so we can retrieve it during the callback query
    context.user_data['current_url'] = url

    # Create the quality selection inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("🎥 1080p (Full HD)", callback_data="quality_1080"),
            InlineKeyboardButton("🎬 720p (HD)", callback_data="quality_720")
        ],
        [
            InlineKeyboardButton("📱 360p (Data Saver)", callback_data="quality_360"),
            InlineKeyboardButton("🎵 Audio Only (MP3)", callback_data="quality_audio")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "✨ **Select your desired download quality:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button clicks for quality selection."""
    query = update.callback_query
    await query.answer()

    url = context.user_data.get('current_url')
    if not url:
        await query.edit_message_text("❌ Session expired. Please send the link again.")
        return

    quality = query.data
    chat_id = query.message.chat_id

    # Translate selection into formatting rules
    quality_names = {
        "quality_1080": "1080p Full HD",
        "quality_720": "720p HD",
        "quality_360": "360p Data Saver",
        "quality_audio": "MP3 Audio"
    }

    selected_name = quality_names.get(quality, "Unknown")
    await query.edit_message_text(f"⏳ **Processing your request for {selected_name}...**\nDownloading from source...")

    cookie_file_path = None
    try:
        # Check if cookies are supplied via environment variable
        cookies_b64 = os.getenv('YT_COOKIES')
        if cookies_b64:
            try:
                temp_cookies = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt')
                decoded_cookies = base64.b64decode(cookies_b64.strip()).decode('utf-8')
                temp_cookies.write(decoded_cookies)
                temp_cookies.close()
                cookie_file_path = temp_cookies.name
            except Exception as cookie_err:
                print(f"Failed to load cookies: {cookie_err}")

        # Use a temporary directory to download the media
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                'outtmpl': os.path.join(tmpdir, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'impersonate': 'chrome', # Attempt Chrome TLS fingerprinting
                
                # Tell FFmpeg to merge the downloaded audio and video streams into a standard mp4 container
                'merge_output_format': 'mp4',
            }

            if cookie_file_path:
                ydl_opts['cookiefile'] = cookie_file_path

            # Format formatting rules (removes strict mp4/m4a extension filters to prevent format errors,
            # letting yt-dlp select the absolute best codecs and merge them to mp4 via ffmpeg)
            if quality == "quality_1080":
                ydl_opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'
            elif quality == "quality_720":
                ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
            elif quality == "quality_360":
                ydl_opts['format'] = 'bestvideo[height<=360]+bestaudio/best[height<=360]/best'
            elif quality == "quality_audio":
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]

            # Download task with fallback for missing impersonation support
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(url, download=True)
                    downloaded_file = ydl.prepare_filename(info_dict)
            except Exception as extract_err:
                err_str = str(extract_err).lower()
                if 'impersonate' in err_str or 'dependency' in err_str or 'target' in err_str:
                    print("⚠️ Impersonate target failed, retrying without browser impersonation...")
                    del ydl_opts['impersonate']
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info_dict = ydl.extract_info(url, download=True)
                        downloaded_file = ydl.prepare_filename(info_dict)
                else:
                    raise extract_err

            # Handle file extension changes (e.g. audio conversion changes ext to .mp3, merging overrides ext to .mp4)
            if quality == "quality_audio":
                base, _ = os.path.splitext(downloaded_file)
                downloaded_file = base + ".mp3"
            else:
                # After merging, the output file format is forced to .mp4
                base, _ = os.path.splitext(downloaded_file)
                downloaded_file = base + ".mp4"

            # Check file size before uploading
            file_size_mb = os.path.getsize(downloaded_file) / (1024 * 1024)
            if file_size_mb > 50.0 and quality != "quality_audio":
                await query.edit_message_text(
                    f"⚠️ **File size exceeds limit!**\n\n"
                    f"The video is **{file_size_mb:.2f} MB**, which exceeds Telegram's **50 MB** upload limit for bots.\n\n"
                    f"👉 Please send the link again and choose a lower resolution (e.g., **720p** or **360p**)."
                )
                return

            await query.edit_message_text("📤 **Uploading file to Telegram...**")

            # Send the file to Telegram
            with open(downloaded_file, 'rb') as f:
                if quality == "quality_audio":
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        caption=info_dict.get('title', 'Audio'),
                        title=info_dict.get('title', 'Audio'),
                        performer=info_dict.get('uploader', 'yt-dlp')
                    )
                else:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        supports_streaming=True,
                        caption=info_dict.get('title', 'Video')
                    )
            
            await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)

    except yt_dlp.utils.DownloadError as e:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ **Download failed.**\nThis video might not have your selected resolution, or anti-bot checks blocked the connection.\n\n*Details:*\n`{str(e)}`",
            parse_mode="Markdown"
        )
    except Exception as e:
         await context.bot.send_message(
             chat_id=chat_id,
             text=f"⚠️ **An error occurred during processing:**\n`{str(e)}`",
             parse_mode="Markdown"
         )
    finally:
        # Clean up temporary cookies file if we created one
        if cookie_file_path and os.path.exists(cookie_file_path):
            try:
                os.unlink(cookie_file_path)
            except Exception:
                pass

def main():
    """Starts the Telegram bot."""
    print("Starting Telegram Bot...")
    
    # Initialize the Application
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Start polling for updates
    print("Bot is polling... Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()

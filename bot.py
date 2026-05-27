import os
import tempfile
import base64
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Replace with your actual Telegram Bot Token from @BotFather
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a greeting message when the /start command is issued."""
    await update.message.reply_text(
        "👋 Hello! Send me a video link (YouTube, Twitter, TikTok, etc.), "
        "and I'll download it for you!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming text messages (URLs)."""
    url = update.message.text
    chat_id = update.message.chat_id

    # Simple validation
    if not url.startswith('http'):
        await update.message.reply_text("❌ Please send a valid URL starting with http/https.")
        return

    # Inform the user that processing has started
    status_msg = await update.message.reply_text("⏳ Downloading video... Please wait.")
    
    cookie_file_path = None
    try:
        # Check if Netscape cookies are supplied via base64 environment variable
        cookies_b64 = os.getenv('YT_COOKIES')
        if cookies_b64:
            try:
                # Decode and write to a temporary file
                temp_cookies = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt')
                decoded_cookies = base64.b64decode(cookies_b64.strip()).decode('utf-8')
                temp_cookies.write(decoded_cookies)
                temp_cookies.close()
                cookie_file_path = temp_cookies.name
            except Exception as cookie_err:
                print(f"Failed to load cookies from environment variable: {cookie_err}")

        # Use a temporary directory to download the media
        with tempfile.TemporaryDirectory() as tmpdir:
            # yt-dlp configuration options
            ydl_opts = {
                # Save file in the temp directory
                'outtmpl': os.path.join(tmpdir, '%(title)s.%(ext)s'),
                
                # Best video + audio format that fits within Telegram's 50MB bot limit, preferably mp4
                'format': 'best[filesize<50M][ext=mp4]/best[filesize<50M]/best',
                
                # Enforce the 50MB size limit (Telegram Bot API limit)
                'max_filesize': 50 * 1024 * 1024, 
                
                'quiet': True,
                'no_warnings': True,
                
                # Bypasses typical cloud IP blocks by impersonating a standard Chrome browser
                'impersonate': 'chrome',
            }

            # Inject the temporary cookies file if it was created successfully
            if cookie_file_path:
                ydl_opts['cookiefile'] = cookie_file_path
            
            # Download using the yt-dlp Python API
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info and download
                info_dict = ydl.extract_info(url, download=True)
                # Get the exact downloaded file path
                downloaded_file = ydl.prepare_filename(info_dict)
                
            # Update status
            await context.bot.edit_message_text(
                chat_id=chat_id, 
                message_id=status_msg.message_id, 
                text="📤 Uploading video to Telegram..."
            )
            
            # Send the video back to the user
            with open(downloaded_file, 'rb') as video:
                await context.bot.send_video(
                    chat_id=chat_id, 
                    video=video, 
                    supports_streaming=True,
                    caption=info_dict.get('title', 'Downloaded via yt-dlp')
                )
                
            # Clean up the status message
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)

    except yt_dlp.utils.DownloadError as e:
        await context.bot.edit_message_text(
            chat_id=chat_id, 
            message_id=status_msg.message_id, 
            text=f"❌ Download failed (File might be larger than 50MB or URL is unsupported).\n\nDetails: {str(e)}"
        )
    except Exception as e:
         await context.bot.edit_message_text(
             chat_id=chat_id, 
             message_id=status_msg.message_id, 
             text=f"⚠️ An error occurred: {str(e)}"
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

    # Start polling for updates
    print("Bot is polling... Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()

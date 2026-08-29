import os
import subprocess
import tempfile
import base64
import glob
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ─── Configuration ───────────────────────────────────────────────────────────
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
TELEGRAM_MAX_SIZE = 49 * 1024 * 1024  # 49 MB safety margin

# ─── Encoding profiles ──────────────────────────────────────────────────────
ENCODE_PROFILES = {
    "480": {"height": 480, "crf": 27, "preset": "veryfast", "level": "4.0", "audio_br": "96k"},
    "720": {"height": 720, "crf": 25, "preset": "veryfast", "level": "4.0", "audio_br": "128k"},
    "1080": {"height": 1080, "crf": 23, "preset": "fast", "level": "4.2", "audio_br": "128k"},
}

# Resolution fallback order (try lower quality if file is too large)
FALLBACK_ORDER = ["1080", "720", "480"]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def is_owner(user_id: int) -> bool:
    """Check if the user is the bot owner."""
    return user_id == OWNER_ID


def get_cookie_file() -> tuple[str | None, str | None]:
    """Decode base64 YT_COOKIES env var or load raw Netscape cookies into a temporary file.
    Returns (temp_file_path, error_message)."""
    cookies_raw = os.getenv("YT_COOKIES")
    if not cookies_raw:
        return None, "YT_COOKIES environment variable is missing"
    
    raw_content = cookies_raw.strip()
    try:
        # Check if the user pasted raw Netscape text directly or base64-encoded it
        if raw_content.startswith("# Netscape") or "youtube.com" in raw_content:
            decoded_bytes = raw_content.encode("utf-8")
        else:
            decoded_bytes = base64.b64decode(raw_content)
            
        tmp = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt", encoding="utf-8")
        tmp.write(decoded_bytes.decode("utf-8"))
        tmp.close()
        return tmp.name, None
    except Exception as e:
        return None, f"Failed to decode cookies: {str(e)}"


def compress_video(input_path: str, output_path: str, profile: dict, extra_crf: int = 0) -> bool:
    """Compress a video using FFmpeg with the given encoding profile.
    Returns True on success, False on failure."""
    crf = profile["crf"] + extra_crf
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"scale=-2:{profile['height']}",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", profile["preset"],
        "-profile:v", "high",
        "-level", profile["level"],
        "-c:a", "aac",
        "-b:a", profile["audio_br"],
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return result.returncode == 0


def extract_audio(input_path: str, output_path: str) -> bool:
    """Extract audio to MP3 using FFmpeg. Returns True on success."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        output_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode == 0:
        return True
    # Fallback: try 96k
    cmd[-1] = output_path  # already set
    cmd[cmd.index("128k")] = "96k"
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return result.returncode == 0


def cleanup_dir(directory: str):
    """Remove all files inside a temporary directory."""
    for f in glob.glob(os.path.join(directory, "*")):
        try:
            os.remove(f)
        except Exception:
            pass


# ─── Telegram Handlers ──────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("🔒 Sorry, this bot is private.")
        return

    welcome = (
        "🎬 *Welcome to your Personal Media Downloader Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 *Download:*\n"
        "  • YouTube videos\n"
        "  • Shorts\n"
        "  • Audio / MP3\n\n"
        "🎚 *Available qualities:*\n"
        "  • 480p\n"
        "  • 720p\n"
        "  • 1080p\n\n"
        "⚡ *Features:*\n"
        "  • Automatic FFmpeg compression before upload\n"
        "  • Optimized size for Telegram upload\n"
        "  • Best possible quality while keeping file size efficient\n"
        "  • Audio extraction\n"
        "  • Automatic temp file cleanup after sending\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📎 Send any YouTube link to begin."
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive a URL and present the quality selection keyboard."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("🔒 Sorry, this bot is private.")
        return

    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text("❌ Please send a valid URL starting with http/https.")
        return

    context.user_data["current_url"] = url

    keyboard = [
        [
            InlineKeyboardButton("📺 480p", callback_data="q_480"),
            InlineKeyboardButton("🎬 720p", callback_data="q_720"),
        ],
        [
            InlineKeyboardButton("🎥 1080p", callback_data="q_1080"),
            InlineKeyboardButton("🎵 Audio MP3", callback_data="q_audio"),
        ],
    ]
    await update.message.reply_text(
        "✨ *Select download quality:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the quality selection and download → compress → upload."""
    query = update.callback_query
    await query.answer()

    if not is_owner(query.from_user.id):
        await query.edit_message_text("🔒 Sorry, this bot is private.")
        return

    url = context.user_data.get("current_url")
    if not url:
        await query.edit_message_text("❌ Session expired. Please send the link again.")
        return

    choice = query.data  # q_480, q_720, q_1080, q_audio
    chat_id = query.message.chat_id
    is_audio = choice == "q_audio"
    target_res = choice.replace("q_", "") if not is_audio else "audio"

    label_map = {"480": "480p", "720": "720p", "1080": "1080p", "audio": "MP3 Audio"}
    label = label_map.get(target_res, target_res)

    status_msg = query.message
    cookie_path, cookie_err = get_cookie_file()
    
    status_text = f"⏳ *Downloading source for {label}…*"
    if cookie_err:
        safe_err = cookie_err.replace("_", "\\_").replace("*", "\\*")
        status_text += f"\n⚠️ Cookie loading warning: {safe_err}"
    await status_msg.edit_text(status_text, parse_mode="Markdown")

    tmpdir = tempfile.mkdtemp(prefix="ytbot_")

    try:
        # ── 1. Download raw source with yt-dlp ──────────────────────────────
        base_opts = {
            "outtmpl": os.path.join(tmpdir, "source.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "check_formats": False,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
            # Force YouTube to use proper player clients instead of the
            # degraded "tv" client that returns only storyboard thumbnails
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "android", "ios"],
                }
            },
        }
        # Optional: YouTube Proof-of-Origin token (bypasses bot checks on some IPs)
        po_token = os.getenv("YT_PO_TOKEN")
        if po_token:
            base_opts["extractor_args"]["youtube"]["po_token"] = [po_token]

        if cookie_path:
            base_opts["cookiefile"] = cookie_path

        # ── Diagnostic: list what formats YouTube is actually offering ────
        print(f"\n=== FORMAT DIAGNOSTIC for {url} ===")
        try:
            diag_opts = {**base_opts, "quiet": False, "listformats": True}
            with yt_dlp.YoutubeDL(diag_opts) as ydl:
                ydl.extract_info(url, download=False)
        except SystemExit:
            pass
        except Exception as diag_e:
            print(f"[diag] Format listing failed: {diag_e}")
        print("=== END FORMAT DIAGNOSTIC ===\n")

        # ── Download with escalating fallbacks ────────────────────────────
        format_attempts = (
            ["bestaudio/best"] if is_audio else
            [None, "best", "worst"]  # None = yt-dlp default
        )

        info = None
        last_err = None
        for fmt in format_attempts:
            try:
                dl_opts = {**base_opts}
                if fmt:
                    dl_opts["format"] = fmt
                print(f"[download] Trying format: {fmt or '(yt-dlp default)'}")
                with yt_dlp.YoutubeDL(dl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                break  # Success
            except Exception as e:
                last_err = e
                print(f"[download] Format '{fmt}' failed: {e}")
                # Clean up any partial downloads before retrying
                for f in glob.glob(os.path.join(tmpdir, "source.*")):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
                continue

        if info is None:
            raise last_err or Exception("All format attempts failed")

        title = info.get("title", "video")

        # Find the downloaded source file
        source_files = glob.glob(os.path.join(tmpdir, "source.*"))
        if not source_files:
            await status_msg.edit_text("❌ Download failed. Try another link.")
            return
        source_path = source_files[0]

        # ── 2. Compress / Extract ────────────────────────────────────────────
        if is_audio:
            await status_msg.edit_text("🎵 *Extracting audio…*", parse_mode="Markdown")
            output_path = os.path.join(tmpdir, "output.mp3")
            if not extract_audio(source_path, output_path):
                await status_msg.edit_text("❌ Audio extraction failed. Try another link.")
                return
        else:
            await status_msg.edit_text(f"🔧 *Compressing to {label}…*", parse_mode="Markdown")

            # Determine the resolution cascade to attempt
            start_idx = FALLBACK_ORDER.index(target_res) if target_res in FALLBACK_ORDER else 0
            resolutions_to_try = FALLBACK_ORDER[start_idx:]

            output_path = None
            for res in resolutions_to_try:
                profile = ENCODE_PROFILES[res]
                candidate = os.path.join(tmpdir, f"output_{res}.mp4")

                # First attempt at base CRF
                if compress_video(source_path, candidate, profile):
                    if os.path.getsize(candidate) <= TELEGRAM_MAX_SIZE:
                        output_path = candidate
                        label = f"{res}p"
                        break

                    # File too large — retry with higher CRF (+2)
                    os.remove(candidate)
                    await status_msg.edit_text(
                        f"🔧 *Re-compressing {res}p with higher compression…*",
                        parse_mode="Markdown",
                    )
                    if compress_video(source_path, candidate, profile, extra_crf=2):
                        if os.path.getsize(candidate) <= TELEGRAM_MAX_SIZE:
                            output_path = candidate
                            label = f"{res}p"
                            break

                # Clean up failed candidate before trying lower resolution
                if os.path.exists(candidate):
                    os.remove(candidate)

                if res != resolutions_to_try[-1]:
                    next_res = resolutions_to_try[resolutions_to_try.index(res) + 1]
                    await status_msg.edit_text(
                        f"⚠️ *{res}p too large. Trying {next_res}p…*",
                        parse_mode="Markdown",
                    )

            if output_path is None:
                await status_msg.edit_text(
                    "❌ Video is too large even at 480p with max compression.\n"
                    "Try a shorter video or use Audio mode."
                )
                return

        # ── 3. Upload to Telegram ────────────────────────────────────────────
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        await status_msg.edit_text(
            f"📤 *Uploading {label} ({file_size_mb:.1f} MB)…*",
            parse_mode="Markdown",
        )

        with open(output_path, "rb") as f:
            if is_audio:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=f,
                    title=title,
                    performer=info.get("uploader", ""),
                    caption=f"🎵 {title}",
                )
            else:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    supports_streaming=True,
                    caption=f"🎬 {title} • {label}",
                )

        await status_msg.edit_text(f"✅ *Done!* Sent {label} — {file_size_mb:.1f} MB", parse_mode="Markdown")

    except yt_dlp.utils.DownloadError as e:
        err_str = str(e)
        print(f"[yt-dlp] DownloadError: {err_str}")
        if "not available" in err_str or "Sign in" in err_str or "bot" in err_str:
            await status_msg.edit_text(
                "❌ *YouTube blocked this request.*\n\n"
                "Your cookies are expired or invalid. YouTube is only returning thumbnail data.\n\n"
                "*To fix:*\n"
                "1. Open your browser and log into YouTube\n"
                "2. Re-export cookies with the extension\n"
                "3. Update `YT_COOKIES` in Railway Variables\n"
                "4. Railway will auto-redeploy",
                parse_mode="Markdown",
            )
        else:
            await status_msg.edit_text("❌ Download failed. Try another link.")
    except Exception as e:
        print(f"[bot] Exception: {e}")
        await status_msg.edit_text("❌ Download failed. Try another link.")
    finally:
        # ── 4. Cleanup ───────────────────────────────────────────────────────
        cleanup_dir(tmpdir)
        try:
            os.rmdir(tmpdir)
        except Exception:
            pass
        if cookie_path and os.path.exists(cookie_path):
            try:
                os.remove(cookie_path)
            except Exception:
                pass


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main():
    print(f"Starting bot… Owner ID: {OWNER_ID}")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("Polling…")
    app.run_polling()


if __name__ == "__main__":
    main()

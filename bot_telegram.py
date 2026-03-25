import io
import logging
import os

from dotenv import load_dotenv
load_dotenv()

import requests
from openai import OpenAI

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bot_telegram")
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

CLAUDE_URL = os.environ.get("CLAUDE_URL", "http://localhost:8080")

openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set")
openai_client = OpenAI(api_key=openai_api_key)

# In-memory map: telegram_user_id -> session_id
user_sessions: dict[int, str] = {}


async def transcribe_voice(update: Update) -> str:
    """Download the voice message and transcribe it with Whisper."""
    voice = update.message.voice
    tg_file = await voice.get_file()
    buf = io.BytesIO()
    await tg_file.download_to_memory(buf)
    buf.seek(0)
    buf.name = "voice.ogg"
    transcript = openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
    )
    return transcript.text


async def send_to_claude(update: Update, user_id: int, prompt: str):
    """Forward a prompt to the Claude server and reply with the result."""
    session_id = user_sessions.get(user_id)

    log.info("Sending to Claude — user_id=%s session_id=%s prompt=%r", user_id, session_id, prompt[:80])

    try:
        resp = requests.post(
            f"{CLAUDE_URL}/run",
            json={
                "prompt": prompt,
                "workdir": f"/workspace/{user_id}",
                "session_id": session_id,
            },
            timeout=200,
        )
        log.debug("Claude server HTTP %d — body: %s", resp.status_code, resp.text[:300])
        data = resp.json()
    except requests.exceptions.Timeout:
        log.warning("Timeout waiting for Claude server")
        await update.message.reply_text("⚠️ Timeout — retry or simplify the request.")
        return
    except Exception as e:
        log.exception("Error calling Claude server")
        await update.message.reply_text(f"❌ Error: {e}")
        return

    output = data.get("output", "No response.")
    new_session_id = data.get("session_id")
    is_question = data.get("is_question", False)

    if new_session_id:
        if is_question:
            user_sessions[user_id] = new_session_id
        else:
            user_sessions.pop(user_id, None)

    if is_question:
        output += "\n\n_💬 Reply to continue..._"

    for chunk in [output[i:i+4096] for i in range(0, len(output), 4096)]:
        await update.message.reply_text(chunk, parse_mode="Markdown")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("⏳ Processing...")
    await send_to_claude(update, user_id, update.message.text)


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    log.info("Voice message from user_id=%s", user_id)
    await update.message.reply_text("🎙️ Transcribing...")

    try:
        transcript = await transcribe_voice(update)
        log.info("Transcription result: %r", transcript)
    except Exception as e:
        log.exception("Whisper transcription failed")
        await update.message.reply_text(f"❌ Transcription error: {e}")
        return

    await update.message.reply_text(f"📝 *Transcription:*\n{transcript}", parse_mode="Markdown")
    await update.message.reply_text("⏳ Processing...")
    await send_to_claude(update, user_id, transcript)


telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
if not telegram_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

app = ApplicationBuilder().token(telegram_token).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.run_polling()

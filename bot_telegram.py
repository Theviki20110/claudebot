import io
import logging
import os
import re
import time

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from telegram import Update, Message
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, SystemMessage, HookMatcher

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bot")

openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set")
openai_client = OpenAI(api_key=openai_api_key)

ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "Glob", "Grep",
    "WebSearch", "WebFetch",
    "Bash(uv *)", "Bash(git *)", "Bash(python *)",
]

# In-memory map: telegram_user_id -> session_id
user_sessions: dict[int, str] = {}

TOOL_ICONS: dict[str, str] = {
    "Read": "📖", "Write": "✍️", "Edit": "✏️",
    "Glob": "🔍", "Grep": "🔎", "Bash": "⚙️",
    "WebSearch": "🌐", "WebFetch": "🌐",
}


def _tool_label(tool_name: str, tool_input: dict) -> str:
    icon = TOOL_ICONS.get(tool_name, "🔧")
    if tool_name in ("Read", "Write", "Edit"):
        path = tool_input.get("file_path", "")
        if path:
            return f"{icon} {tool_name}: `{os.path.basename(path)}`"
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")[:50]
        return f"{icon} `{cmd}`"
    if tool_name == "WebSearch":
        q = tool_input.get("query", "")[:50]
        return f"{icon} Searching: _{q}_"
    if tool_name == "WebFetch":
        url = tool_input.get("url", "")[:60]
        return f"{icon} Fetching: `{url}`"
    if tool_name in ("Glob", "Grep"):
        pattern = tool_input.get("pattern", tool_input.get("glob", ""))[:40]
        return f"{icon} {tool_name}: `{pattern}`"
    return f"{icon} {tool_name}…"


def is_question(text: str) -> bool:
    if not text:
        return False
    if "?" in text:
        return True
    patterns = [
        r"\bche tipo\b", r"\bquale\b", r"\bquali\b", r"\bdimmi\b",
        r"\bspecifica\b", r"\bpreferis\w+\b", r"\bvuoi\b", r"\bdesideri\b",
        r"\bscegli\b", r"\bopzion\w+\b", r"\bpuoi indicare\b",
    ]
    return any(re.search(p, text.lower()) for p in patterns)


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


async def run_claude(
    user_id: int,
    prompt: str,
    status_callback=None,
) -> tuple[str, str | None]:
    """Run the Claude agent and return (output, new_session_id).

    status_callback(text) is called before each tool use with a short
    human-readable description of what Claude is about to do.
    """
    session_id = user_sessions.get(user_id)
    workdir = f"/workspace/{user_id}"
    os.makedirs(workdir, exist_ok=True)

    log.info("Running Claude — user_id=%s session_id=%s prompt=%r", user_id, session_id, prompt[:80])

    # Throttle Telegram edits: at most one per second
    _last_edit: list[float] = [0.0]

    async def on_pre_tool(input_data, tool_use_id, context):
        if status_callback:
            tool_name = input_data.get("tool_name", "tool")
            tool_input = input_data.get("tool_input", {})
            label = _tool_label(tool_name, tool_input)
            now = time.monotonic()
            if now - _last_edit[0] >= 1.0:
                _last_edit[0] = now
                await status_callback(label)
        return {}

    options = ClaudeAgentOptions(
        cwd=workdir,
        allowed_tools=ALLOWED_TOOLS,
        max_turns=10,
        permission_mode="acceptEdits",
        resume=session_id,
        hooks={
            "PreToolUse": [HookMatcher(matcher=".*", hooks=[on_pre_tool])]
        },
    )

    result_text = "No response."
    new_session_id = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, SystemMessage) and message.subtype == "init":
            new_session_id = message.data.get("session_id")
            log.debug("Session started: %s", new_session_id)
        elif isinstance(message, ResultMessage):
            result_text = message.result or "No response."
            log.info("Claude result — session=%s output=%r", new_session_id, result_text[:120])

    return result_text, new_session_id


async def send_to_claude(update: Update, user_id: int, prompt: str):
    """Run Claude and send the reply back to the user."""
    status_msg: Message = await update.message.reply_text("⏳ Starting…")

    async def update_status(label: str):
        try:
            await status_msg.edit_text(f"⏳ {label}", parse_mode="Markdown")
        except Exception:
            pass  # ignore "message not modified" and similar errors

    try:
        output, new_session_id = await run_claude(user_id, prompt, status_callback=update_status)
    except Exception as e:
        log.exception("Claude agent error")
        await status_msg.edit_text(f"❌ Error: {e}")
        return

    # Remove the status message now that we have the result
    try:
        await status_msg.delete()
    except Exception:
        pass

    question = is_question(output)

    if new_session_id:
        if question:
            user_sessions[user_id] = new_session_id
        else:
            user_sessions.pop(user_id, None)

    if question:
        output += "\n\n_💬 Reply to continue..._"

    for chunk in [output[i:i + 4096] for i in range(0, len(output), 4096)]:
        await update.message.reply_text(chunk, parse_mode="Markdown")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await send_to_claude(update, user_id, update.message.text)


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    log.info("Voice message from user_id=%s", user_id)
    status_msg: Message = await update.message.reply_text("🎙️ Transcribing…")

    try:
        transcript = await transcribe_voice(update)
        log.info("Transcription result: %r", transcript)
    except Exception as e:
        log.exception("Whisper transcription failed")
        await status_msg.edit_text(f"❌ Transcription error: {e}")
        return

    await status_msg.edit_text(f"📝 *Transcription:*\n{transcript}", parse_mode="Markdown")
    await send_to_claude(update, user_id, transcript)


telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
if not telegram_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

app = ApplicationBuilder().token(telegram_token).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.run_polling()

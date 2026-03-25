# telegram-claude-agent

A Telegram bot that lets you interact with [Claude Code](https://github.com/anthropics/claude-code) as an AI agent directly from chat. Supports both text and voice messages.

```
User (text/voice) → Telegram Bot → FastAPI server → Claude Code CLI → response
```

Each user gets an isolated workspace and multi-turn conversation support via session IDs.

## How it works

- **`bot_telegram.py`** — Telegram bot. Receives text and voice messages, transcribes audio via OpenAI Whisper, forwards prompts to the Claude server.
- **`claude_server.py`** — FastAPI server. Runs the `claude` CLI as a subprocess and exposes a `/run` endpoint.

## Requirements

- Docker & Docker Compose
- An `ANTHROPIC_API_KEY` from [console.anthropic.com](https://console.anthropic.com) (must start with `sk-ant-api03-`)
- An `OPENAI_API_KEY` for Whisper transcription
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))

## Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/your-username/telegram-claude-agent.git
   cd telegram-claude-agent
   ```

2. Create a `.env` file:
   ```env
   ANTHROPIC_API_KEY=sk-ant-api03-...
   OPENAI_API_KEY=sk-...
   TELEGRAM_BOT_TOKEN=...
   ```

3. Start with Docker Compose:
   ```bash
   docker compose up --build
   ```

## Voice messages

Send a voice message to the bot and it will:
1. Transcribe it with OpenAI Whisper
2. Show the transcription in chat
3. Forward the text to Claude as a normal prompt

## Tools available to the agent

The Claude agent can use: `Read`, `Write`, `Edit`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, `Bash` (limited to `uv`, `git`, `python` commands).

## Notes

- Each user's files live in `./workspace/<user_id>`.
- Sessions are kept in memory — they reset on restart.
- Telegram messages are capped at 4096 characters; longer responses are split automatically.

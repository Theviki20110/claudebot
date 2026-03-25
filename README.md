# telegram-claude-agent

A Telegram bot that lets you interact with [Claude Code](https://github.com/anthropics/claude-code) as an AI agent directly from chat.

```
User → Telegram Bot → Flask API → Claude Code CLI → response
```

Each user gets an isolated workspace and multi-turn conversation support via session IDs.

## How it works

- **`bot_telegram.py`** — Telegram bot. Receives messages, calls the API, replies with the result.
- **`claude_server.py`** — Flask server. Runs `claude` CLI as a subprocess and exposes a `/run` endpoint.

## Requirements

- Docker & Docker Compose
- An `ANTHROPIC_API_KEY`
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))

## Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/your-username/telegram-claude-agent.git
   cd telegram-claude-agent
   ```

2. Create a `.env` file:
   ```env
   ANTHROPIC_API_KEY=your_anthropic_key
   TELEGRAM_BOT_TOKEN=your_telegram_token
   API_SECRET=change_me
   ```

3. Set the token and secret in the source files (or better, read them from env vars).

4. Start with Docker Compose:
   ```bash
   docker compose up --build
   ```

## Tools available to the agent

The Claude agent can use: `Read`, `Write`, `Edit`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, `Bash` (limited to `uv`, `git`, `python` commands).

## Notes

- Each user's files live in `/workspace/<user_id>` inside the container.
- Sessions are kept in memory — they reset on restart.
- Telegram messages are capped at 4096 characters; longer responses are split automatically.

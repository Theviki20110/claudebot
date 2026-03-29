FROM python:3.12-slim

# Node.js required at runtime by the Claude Code CLI (bundled with claude-agent-sdk)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .

COPY uv.lock .

RUN uv sync --no-cache

COPY bot_telegram.py ./

RUN mkdir -p /workspace

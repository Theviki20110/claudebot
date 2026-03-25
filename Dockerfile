FROM python:3.12-slim

# Install Node.js (for claude CLI) and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://claude.ai/install.sh | bash

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .

COPY uv.lock .

RUN uv sync --no-cache

COPY claude_server.py bot_telegram.py ./

RUN mkdir -p /workspace

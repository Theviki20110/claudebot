import json
import logging
import os
import re
import subprocess
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("claude_server")

app = FastAPI()

log.info("Startup — ANTHROPIC_API_KEY present: %s", bool(os.environ.get("ANTHROPIC_API_KEY")))


class RunRequest(BaseModel):
    prompt: str
    workdir: str = "/workspace"
    session_id: Optional[str] = None


def run_claude(prompt: str, workdir: str = "/workspace", session_id: Optional[str] = None):
    os.makedirs(workdir, exist_ok=True)
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--allowedTools", "Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,Bash(uv *),Bash(git *),Bash(python *)",
        "--max-turns", "10",
    ]
    if session_id:
        cmd += ["--resume", session_id]

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    log.debug("ANTHROPIC_API_KEY prefix: %s", key[:12] if key else "<not set>")
    log.debug("Running command: %s", cmd)
    log.debug("workdir: %s | session_id: %s", workdir, session_id)

    result = subprocess.run(
        cmd,
        capture_output=True, text=True,
        cwd=workdir, timeout=180,
    )

    log.debug("returncode: %d", result.returncode)
    log.debug("stdout: %s", result.stdout[:500] if result.stdout else "<empty>")
    log.debug("stderr: %s", result.stderr[:500] if result.stderr else "<empty>")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        log.warning("Could not parse stdout as JSON, returning raw")
        data = {"result": result.stdout, "type": "raw"}

    return data, result.returncode


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


@app.post("/run")
def run(body: RunRequest):
    log.info("POST /run — prompt=%r workdir=%s session_id=%s", body.prompt[:80], body.workdir, body.session_id)

    data, returncode = run_claude(body.prompt, body.workdir, body.session_id)

    result_text = data.get("result", "")
    log.info("Claude response — returncode=%d output=%r", returncode, result_text[:120])
    return {
        "output": result_text,
        "session_id": data.get("session_id"),
        "returncode": returncode,
        "cost_usd": data.get("total_cost_usd"),
        "is_question": is_question(result_text),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)

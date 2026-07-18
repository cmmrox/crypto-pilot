"""Summary provider: turns collected items into a neutral market briefing.

CodexProvider runs the fixed BSD §11 prompt through the Codex SDK (gpt-5.5), no
workspace/tools — text in, JSON out. A provider failure degrades gracefully; the
news module never touches trading (isolation enforced by import-linter).
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

_log = get_logger("news_provider")

PROMPT = (
    "You are a neutral market-news summariser for a BTC trader. From the items below, "
    "write 5-8 concise, market-relevant bullets. Neutral tone. Flag anything that could "
    "affect BTC volatility (regulation, ETF flows, Fed/CPI/FOMC). Do NOT give trading "
    "advice. Respond ONLY with JSON: "
    '{"sentiment": "one of Bearish|Cautious|Neutral|Neutral-positive|Positive", '
    '"bullets": [{"text": "...", "source": "..."}]}. Items:\n'
)


@dataclass(frozen=True)
class Briefing:
    sentiment: str
    bullets: list[dict[str, str]]
    model: str


class SummaryProvider(Protocol):
    async def summarize(self, items: list[dict[str, str]]) -> Briefing: ...


def _parse(text: str, model: str) -> Briefing:
    """Parse the model's JSON response defensively."""
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            bullets = [
                {"text": str(b.get("text", "")), "source": str(b.get("source", ""))}
                for b in data.get("bullets", [])
                if b.get("text")
            ]
            if bullets:
                return Briefing(str(data.get("sentiment", "Neutral")), bullets, model)
        except (ValueError, TypeError, AttributeError):
            pass
    # Fallback: wrap the raw text as a single bullet.
    return Briefing("Neutral", [{"text": text.strip()[:400], "source": ""}], model)


def _resolve_codex_bin() -> str:
    """Locate the bundled codex binary."""
    from openai_codex.client import _resolve_codex_bin as _r

    return str(_r(type("C", (), {"codex_bin": None})()))


class CodexProvider:
    """Summarise via the `codex exec` binary using the ChatGPT device-code session.

    We shell out to the binary (not the SDK's thread.run, which uses the API-key
    Responses endpoint) so the owner's device-code login is what authenticates.
    text in → final message out (parsed as JSON). Hard timeout + one retry.
    """

    def __init__(self, *, timeout_s: float = 120.0) -> None:
        self._timeout = timeout_s

    async def summarize(self, items: list[dict[str, str]]) -> Briefing:
        import asyncio
        import os
        import tempfile

        settings = get_settings()
        env = dict(os.environ, CODEX_HOME=settings.codex_home)
        prompt = PROMPT + "\n".join(f"- {i['title']} ({i['source']})" for i in items[:40])
        codex_bin = _resolve_codex_bin()

        last_err = ""
        for attempt in range(2):
            with tempfile.NamedTemporaryFile("r", suffix=".txt", delete=False) as tf:
                out_path = tf.name
            try:
                proc = await asyncio.create_subprocess_exec(
                    codex_bin, "exec", "--skip-git-repo-check",
                    "-m", settings.news_model,
                    "--output-last-message", out_path,
                    prompt,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
                except TimeoutError:
                    proc.kill()
                    last_err = "codex exec timed out"
                    continue
                text = ""
                try:
                    with open(out_path) as fh:
                        text = fh.read().strip()
                except OSError:
                    text = ""
                if proc.returncode == 0 and text:
                    return _parse(text, settings.news_model)
                last_err = (stderr.decode()[-300:] if stderr else "") or "empty response"
                _log.warning("codex_exec_failed", attempt=attempt, detail=last_err)
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(out_path)
        raise RuntimeError(f"codex summarize failed: {last_err}")

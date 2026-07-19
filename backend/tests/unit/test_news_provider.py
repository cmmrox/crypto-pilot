"""Unit tests for news summary parsing (QA-8)."""

from __future__ import annotations

from app.news.provider import _codex_args, _parse, _subprocess_environment


def test_parse_valid_json() -> None:
    text = '{"sentiment": "Positive", "bullets": [{"text": "ETF inflows", "source": "CoinDesk"}]}'
    b = _parse(text, "gpt-5.5")
    assert b.sentiment == "Positive"
    assert b.bullets[0]["text"] == "ETF inflows"
    assert b.model == "gpt-5.5"


def test_parse_json_embedded_in_prose() -> None:
    text = 'Here you go:\n{"sentiment":"Neutral","bullets":[{"text":"x","source":"y"}]}\nThanks'
    b = _parse(text, "gpt-5.5")
    assert b.sentiment == "Neutral"


def test_parse_garbage_falls_back() -> None:
    b = _parse("totally not json", "gpt-5.5")
    assert b.sentiment == "Neutral"
    assert len(b.bullets) == 1


def test_codex_subprocess_isolated_from_backend_secrets(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CP_MASTER_KEY", "secret-master")
    monkeypatch.setenv("CP_JWT_SECRET", "secret-jwt")
    monkeypatch.setenv("CP_DATABASE_URL", "postgresql://secret")
    env = _subprocess_environment("/codex-auth", "/isolated")
    assert env["CODEX_HOME"] == "/codex-auth"
    assert env["HOME"] == "/isolated"
    assert not any(name.startswith("CP_") for name in env)

    args = _codex_args(
        "/bin/codex",
        model="gpt-5.5",
        cwd="/isolated",
        output_path="/isolated/out.json",
    )
    assert "--ephemeral" in args
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert args[-1] == "-"

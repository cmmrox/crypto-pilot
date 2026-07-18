"""Unit tests for news summary parsing (QA-8)."""

from __future__ import annotations

from app.news.provider import _parse


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

"""Malformed manifests must never enter the live strategy catalog."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from app.strategies import default_strategy, registered_strategies
from app.strategies.__main__ import main
from app.strategies.catalog import _validate_all


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("contract_version", 999, "unsupported contract"),
        ("strategy_id", "invalid", "lowercase name"),
        ("strategy_id", "valid_1h", "does not match"),
        ("packaged_default", False, "exactly one"),
    ],
)
def test_invalid_manifest_rejected(field, value, expected):
    manifest = replace(default_strategy().manifest, **{field: value})
    with pytest.raises(RuntimeError, match=expected):
        _validate_all([SimpleNamespace(manifest=manifest)])


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("decision_point", "open_candle", "closed candles"),
        ("warmup_bars", 0, "must be positive"),
        ("history_bars", 1, "cover the warmup"),
    ],
)
def test_invalid_data_policy_rejected(field, value, expected):
    manifest = default_strategy().manifest
    invalid = replace(manifest, market=replace(manifest.market, **{field: value}))
    with pytest.raises(RuntimeError, match=expected):
        _validate_all([SimpleNamespace(manifest=invalid)])


def test_unverified_release_and_duplicate_alias_rejected():
    manifest = default_strategy().manifest
    invalid = replace(manifest, validation=replace(manifest.validation, status="unverified"))
    with pytest.raises(RuntimeError, match="not verified"):
        _validate_all([SimpleNamespace(manifest=invalid)])
    with pytest.raises(RuntimeError, match="duplicate legacy"):
        _validate_all([SimpleNamespace(manifest=manifest), SimpleNamespace(manifest=manifest)])


def test_catalog_cli_lists_pinned_releases_and_default(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["catalog", "list"])
    assert main() == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == len(registered_strategies())
    assert {row["strategy_id"] for row in rows} == {
        "trend_rider_v6_4h",
        "trend_rider_v52_4h",
        "trend_rider_refined_v1_4h",
        "atlas_dual_v1_4h",
    }
    assert sum(row["packaged_default"] for row in rows) == 1
    monkeypatch.setattr("sys.argv", ["catalog", "validate"])
    assert main() == 0
    assert "default=trend_rider_v6_4h" in capsys.readouterr().out

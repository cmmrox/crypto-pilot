"""Advisor errors never substitute a parameter decision or start the trading app."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from app.experiment_lab.advisor import run_once
from app.experiment_lab.candidate import candidate_for_parity


async def test_codex_adapter_isolates_credentials_and_separates_research_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.experiment_lab.advisor import AdvisorSettings, CodexAdvisor

    captured: dict = {}
    monkeypatch.setattr("openai_codex.client._resolve_codex_bin", lambda _: "/test/codex")
    monkeypatch.setenv("CP_BINANCE_SECRET", "test-must-not-be-inherited")

    async def spawn(*arguments, **kwargs):
        captured.update(arguments=arguments, environment=kwargs["env"])
        schema = Path(arguments[arguments.index("--output-schema") + 1])
        captured["schema"] = json.loads(schema.read_text())
        output = Path(arguments[arguments.index("--output-last-message") + 1])
        output.write_text(json.dumps({"summary": "test structured response"}))
        process = AsyncMock()
        process.returncode = 0

        async def communicate(prompt):
            captured["prompt"] = prompt.decode()
            return None, None

        process.communicate.side_effect = communicate
        return process

    monkeypatch.setattr("asyncio.create_subprocess_exec", spawn)
    provider = CodexAdvisor(
        AdvisorSettings(
            lab_url="http://lab-test",
            lab_service_token="test-advisor-token",
            codex_home=str(tmp_path),
        )
    )
    assert await provider.evaluate("REVIEW", {"iteration": {"id": "current-run"}}) == {
        "summary": "test structured response"
    }
    assert "CP_BINANCE_SECRET" not in captured["environment"]
    assert captured["environment"]["CODEX_HOME"] == str(tmp_path)
    assert "--ignore-user-config" in captured["arguments"]
    assert "features.shell_tool=false" in captured["arguments"]
    assert captured["schema"]["properties"]["summary"]["maxLength"] == 3000
    assert captured["schema"]["properties"]["evidence_ids"]["items"]["enum"] == ["current-run"]
    assert (
        "do not use that flag as a parameter-hypothesis falsification criterion"
        in captured["prompt"]
    )


def test_advisor_projection_preserves_numbers_and_counterevidence_without_mutation() -> None:
    from copy import deepcopy

    from app.experiment_lab.context import advisor_context

    lesson = {
        "study_id": "study",
        "iteration_id": "prior",
        "content": {
            "summary": "duplicate",
            "lesson": "learned",
            "counterevidence": "failed",
            "next_hypothesis": "test",
        },
    }
    context = {
        "study": {"id": "study"},
        "lessons": [lesson],
        "strategy_lessons": [lesson, lesson | {"study_id": "other"}],
        "history": [
            {
                "id": str(i),
                "parameters": {"risk_pct": "1.5"},
                "review": {"summary": "duplicate"},
                "result": {
                    "metrics": {"net_profit": "100.123456789", "monthly": [{"return": "-0.05"}]}
                },
            }
            for i in range(22)
        ],
    }
    original = deepcopy(context)
    output = advisor_context(context)
    assert context == original
    assert len(output["strategy_lessons"]) == 1
    assert output["lessons"][0]["content"]["counterevidence"] == "failed"
    for row in output["history"]:
        assert row["parameters"] == {"risk_pct": "1.5"}
        assert row["result"]["metrics"]["net_profit"] == "100.123456789"
    assert "monthly" in output["history"][0]["result"]["metrics"]
    assert "monthly_detail" in output["history"][3]


async def test_advisor_failure_is_reported_without_completion() -> None:
    client = AsyncMock()
    client.request.side_effect = [{"id": "job", "token": "test-lease", "context": {}}, None]
    provider = AsyncMock()
    provider.evaluate.side_effect = ValueError("invalid structured output")
    assert await run_once(client, provider, "SELECT")
    assert client.request.call_args_list[-1].args[1] == "/jobs/job/fail"
    assert not any("complete" in call.args[1] for call in client.request.call_args_list)


async def test_idle_advisor_does_not_call_provider() -> None:
    client = AsyncMock()
    client.request.return_value = None
    provider = AsyncMock()
    assert not await run_once(client, provider, "SELECT")
    provider.evaluate.assert_not_called()


def test_candidate_adapter_does_not_allow_activation_or_unsupported_timeframe() -> None:
    bundle = {
        "schema_version": 1,
        "family": "trend_rider_v6_4h",
        "symbol": "BTCUSDT",
        "interval": "4h",
        "parameters": {"stop_atr": "2.6"},
        "activation_allowed": False,
    }
    assert candidate_for_parity(bundle).parameters.stop_atr == 2.6
    with pytest.raises(ValueError, match="runtime support"):
        candidate_for_parity(bundle | {"interval": "30m"})
    with pytest.raises(ValueError, match="activation"):
        candidate_for_parity(bundle | {"activation_allowed": True})

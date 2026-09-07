"""Strict, versioned requests shared by HTTP and durable jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from strategy_runtime.parameters import INTERVAL_MINUTES, validate_parameters


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StudyInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    strategy_id: Literal["trend_rider_v6_4h"] = "trend_rider_v6_4h"
    dataset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    start: datetime
    end: datetime
    interval: Literal["30m", "1h", "4h"] = "4h"
    fidelity: Literal["CANDLE_REPLAY", "TRADE_REPLAY"] = "CANDLE_REPLAY"
    initial_capital: str = "100"
    parameters: dict[str, str] = Field(default_factory=dict)
    pinned: list[str] = Field(default_factory=list)

    @field_validator("parameters")
    @classmethod
    def parameters_valid(cls, value: dict[str, str]) -> dict[str, str]:
        return validate_parameters(value)

    @field_validator("start", "end")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("UTC-aware timestamps are required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def valid_study(self) -> StudyInput:
        self.parameters = validate_parameters(self.parameters)
        if self.end <= self.start or self.end > datetime.now(timezone.utc):
            raise ValueError("Choose a completed historical period")
        seconds = INTERVAL_MINUTES[self.interval] * 60
        if any(value.timestamp() % seconds for value in (self.start, self.end)):
            raise ValueError(
                "Study boundaries must align with the selected UTC candle interval"
            )
        try:
            capital = Decimal(self.initial_capital)
        except InvalidOperation as error:
            raise ValueError("Initial capital must be a decimal amount") from error
        if not capital.is_finite() or not Decimal("0") < capital <= Decimal(
            "100000000"
        ):
            raise ValueError("Initial capital must be positive and finite")
        if set(self.pinned) - self.parameters.keys():
            raise ValueError("Unknown pinned parameter")
        return self


class IterationInput(StrictModel):
    mode: Literal["ADVISED", "MANUAL", "REPRODUCE"] = "ADVISED"
    parameters: dict[str, str] = Field(default_factory=dict)
    source_iteration_id: str | None = None


class Advice(StrictModel):
    parameters: dict[str, str]
    hypothesis: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(max_length=20)
    uncertainty: str = Field(min_length=1, max_length=1000)
    falsification: str = Field(min_length=1, max_length=1000)


class Review(StrictModel):
    summary: str = Field(min_length=1, max_length=3000)
    lesson: str = Field(min_length=1, max_length=2000)
    counterevidence: str = Field(min_length=1, max_length=2000)
    next_hypothesis: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(max_length=20)


class Completion(StrictModel):
    lease_token: str
    output: dict[str, object]


class LeaseRequest(StrictModel):
    kind: Literal["SELECT", "REPLAY", "REVIEW"]


class LeaseToken(StrictModel):
    lease_token: str


class Failure(LeaseToken):
    error_code: str = "WORKER_FAILED"

    @field_validator("error_code")
    @classmethod
    def known_code(cls, value: str) -> str:
        from experiment_lab.domain.failures import FAILURES

        if value not in FAILURES:
            raise ValueError("Unknown public failure code")
        return value

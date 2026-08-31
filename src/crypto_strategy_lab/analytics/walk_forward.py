from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crypto_strategy_lab.domain import require_utc


class WalkForwardPlan(BaseModel):
    """Declarative gate only. This module intentionally has no execution function."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "walk-forward-plan-v1"
    train_days: int = Field(default=90, gt=0)
    validation_days: int = Field(default=30, gt=0)
    step_days: int = Field(default=30, gt=0)
    start: datetime
    end: datetime
    execute: bool = False

    @model_validator(mode="after")
    def validate_plan(self) -> WalkForwardPlan:
        require_utc(self.start)
        require_utc(self.end)
        if self.start + timedelta(days=self.train_days + self.validation_days) > self.end:
            raise ValueError("walk-forward range is too short")
        if self.execute:
            raise ValueError("long walk-forward execution is outside the current gate")
        return self

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CRYPTO_LAB_", env_file=".env")

    database_url: str = (
        "postgresql+psycopg://crypto_lab:crypto_lab_local@localhost:54329/crypto_strategy_lab"
    )
    report_dir: Path = Path("reports")
    initial_capital: Decimal = Decimal("80")
    max_exposure: Decimal = Field(default=Decimal("0.75"), ge=0, le=1)
    reserve_ratio: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    fee_rate: Decimal = Field(default=Decimal("0.001"), ge=0)
    spread_rate: Decimal = Field(default=Decimal("0.0002"), ge=0)
    slippage_rate: Decimal = Field(default=Decimal("0.0003"), ge=0)

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GH_",
        env_file=".env",
        extra="ignore",
    )

    DATA_DIR: Path = Path("/data")

    @property
    def resolved_data_dir(self) -> Path:
        """Return DATA_DIR, falling back to local ./data if /data is not writable (e.g. non-root/macOS)."""
        p = self.DATA_DIR
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except (PermissionError, OSError):
            fallback = Path.cwd() / "data"
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
    DATABASE_URL: str | None = None
    DEFAULT_MODE: Literal["off", "observe", "shadow", "suggest", "auto"] = "observe"
    GLOBAL_KILL: bool = False
    OBSERVATION_DAYS: int = 10
    MIN_CLUSTER_REQUESTS: int = 200
    MIN_RECURRENCE_DAYS: int = 3
    GATE_MARGIN: float = 3.0
    MIN_SAVINGS_PCT: float = 0.30
    DELTA: float = 0.05
    DAILY_OPTIMIZER_BUDGET_USD: float = 20.0
    JUDGE_MODEL: str | None = None
    PROPOSER_MODEL: str | None = None
    INTERNAL_KEY: str | None = None
    GATEWAY_URL: str = "http://gateway:4000"
    PAYLOAD_TTL_DAYS: int = 30
    POLICY_POLL_SECONDS: float = 5.0
    ADMIN_TOKEN: str | None = None
    AUTO_APPROVE: bool = False

    def require(self, *names: str) -> None:
        """Validate that required environment variables / attributes are set."""
        missing: list[str] = []
        for name in names:
            # Strip GH_ prefix if provided for convenience
            attr = name[3:] if name.startswith("GH_") else name
            val = getattr(self, attr, None)
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(f"GH_{attr}")
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()

from pathlib import Path

import pytest

from gateway_harness.settings import Settings, get_settings


def test_settings_defaults():
    s = Settings()
    assert s.DATA_DIR == Path("/data")
    assert s.DATABASE_URL is None
    assert s.DEFAULT_MODE == "observe"
    assert s.GLOBAL_KILL is False
    assert s.OBSERVATION_DAYS == 10
    assert s.DAILY_OPTIMIZER_BUDGET_USD == 20.0
    assert s.POLICY_POLL_SECONDS == 5.0


def test_settings_require_success():
    s = Settings(DATABASE_URL="postgresql://localhost/test", JUDGE_MODEL="claude-3-5-sonnet")
    s.require("DATABASE_URL", "GH_JUDGE_MODEL")


def test_settings_require_missing():
    s = Settings()
    with pytest.raises(ValueError, match="Missing required configuration: GH_DATABASE_URL, GH_JUDGE_MODEL"):
        s.require("DATABASE_URL", "GH_JUDGE_MODEL")


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("GH_DAILY_OPTIMIZER_BUDGET_USD", "50.0")
    monkeypatch.setenv("GH_DEFAULT_MODE", "shadow")
    s = Settings()
    assert s.DAILY_OPTIMIZER_BUDGET_USD == 50.0
    assert s.DEFAULT_MODE == "shadow"


def test_get_settings_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2

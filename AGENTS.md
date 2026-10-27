# Global rules for Gateway-Harness Appliance

1. **Stack:** Python 3.12, `uv`, `pydantic` v2, `fastapi`, `duckdb`, `pyarrow`, `asyncpg`, `pytest` + `pytest-asyncio`, `ruff`. No other dependencies without asking.
2. **Never edit `repos/litellm/` or `repos/harness2/`.** They are read-only references. Never import from `litellm_enterprise` or `enterprise/` (separate commercial license).
3. **Only create or modify the files listed in your card.** If you need another file changed, stop and report.
4. **Hot-path rule:** code under `gateway_harness/routing/` and `gateway_harness/capture/hook.py` must not do blocking I/O, must not import `duckdb`, must not call any LLM, and must not raise. On any internal error, log and pass the request through unchanged.
5. **Pure modules** (`fingerprint.py`, `scrub.py`, `probe/stats.py`, `probe/validators.py`, `policy/matcher.py`) have no I/O, no globals mutated, and no network. They are 100% unit-testable.
6. **Configuration** comes only from `gateway_harness.settings.get_settings()`. No `os.environ` reads elsewhere.
7. **Unit tests use no network.** For anything that calls a model, use LiteLLM's `mock_response="..."` parameter, or inject a fake client (`Protocol` defined in contracts).
8. **Types:** every public function is fully type-annotated. Use dataclasses or pydantic models from `contracts.py`; never pass raw dicts across module boundaries.
9. **Logging:** `logger = logging.getLogger(__name__)`. Never log message content or API keys.
10. **If the card's spec contradicts what you see in the LiteLLM source, stop and report the contradiction with file and line.** Do not improvise.
11. **Definition of done:** `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` passes, plus the card's own acceptance commands.

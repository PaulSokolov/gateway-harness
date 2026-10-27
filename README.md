# ⚡ Gateway-Harness

[![CI](https://github.com/your-org/gateway-harness/actions/workflows/release.yml/badge.svg)](https://github.com/your-org/gateway-harness/actions)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![LiteLLM](https://img.shields.io/badge/LiteLLM-1.106.4-orange.svg)](https://github.com/BerriAI/litellm)
[![Harness²](https://img.shields.io/badge/Google%20Research-Harness%C2%B2-red.svg)](https://github.com/google-research/harness2)

> **Self-hosted, intelligent, cost-optimizing LLM proxy appliance.**  
> Built by unifying **LiteLLM** (drop-in OpenAI / OpenRouter proxy gateway) and **Google Research Harness²** (recursive prompt scaffolding & contrastive probe methodology).

---

## Table of Contents
1. [Core Features & Architecture](#core-features--architecture)
2. [What `GH_` Stands For](#what-gh_-stands-for)
3. [Secrets & Credentials Guide](#secrets--credentials-guide)
4. [Running with Docker & Docker Compose](#running-with-docker--docker-compose)
5. [Running on Windows & WSL2](#running-on-windows--wsl2)
6. [Meta Hackathon Demo Runbook](#meta-hackathon-demo-runbook)
7. [Developer & Testing Guide](#developer--testing-guide)
8. [Publishing as a Standalone Repository](#publishing-as-a-standalone-repository)

---

## Core Features & Architecture

```
[ Clients / Apps ] 
        │ (OpenAI / OpenRouter API calls on /v1/chat/completions)
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        GATEWAY (LiteLLM Proxy)                         │
│  • Hot-path In-Memory Matcher (< 20 µs)                                │
│  • Model Rewriting (e.g. gpt-4o ➔ gpt-4o-mini) + Scaffold Injection    │
│  • PII Scrubber (Luhn CC, JWT, API keys < 0.5 ms)                      │
│  • Non-blocking Spool Buffer                                           │
└───────────────────┬────────────────────────────────────────────────────┘
                    │ Rotated .jsonl files
                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        WORKER (Background Engine)                      │
│  • Ingest: Spool ➔ Partitioned Parquet + DuckDB Ledger                 │
│  • Funnel: Zero-LLM deterministic clustering & 3x ROI feasibility gate │
│  • Harness² Propose-Probe-Compose: Recursive scaffolding optimizer     │
│  • Contrastive Probe: Position-swapped pairwise judge ($A/B$ and $B/A$)│
│  • Safety: Continuous 5% canary evaluation + automated tripwire        │
└───────────────────┬────────────────────────────────────────────────────┘
                    │ Audited mutations & policies
                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  ADMIN & DASHBOARD (Port 8000)                         │
│  • Real-time realized net savings ticker & financial accounting        │
│  • Human proposal review (Approve / Reject)                            │
│  • Emergency instant kill switch (100% fail-safe pass-through)         │
│  • Embedded htmx UI (zero CDN dependencies, 100% air-gapped support)   │
└────────────────────────────────────────────────────────────────────────┘
```

- **Drop-in Compatible:** Works immediately with any OpenAI SDK, LangChain, LlamaIndex, or OpenRouter integration by changing `base_url` to `http://localhost:4000/v1`.
- **Zero-Downtime Cold Observation:** Passively records production traces into a local DuckDB + Parquet ledger without modifying traffic until enough volume and recurring patterns are proven.
- **Zero-LLM Feasibility Gating:** Analyzes repeating prompt templates and shapes deterministically. Demands volume, active recurrence days, and a **$3\times$ economic return** on probe evaluation cost before spending a single optimizer token.
- **Harness² Recursive Scaffolding ($c_1$ Prompts & Parameters):** If a cheaper model fails initial evaluation, the engine extracts failure patterns and synthesizes targeted system prompt addenda and parameter adjustments until quality reaches parity.
- **Position-Swapped Pairwise Judging:** Completely eliminates position bias ($A$-first vs $B$-first) using contrastive judging.
- **Continuous 5% Canary Guard & Circuit Breaker:** Actively rerouted traffic continuously runs a 5% background canary test against the requested baseline model. If quality regresses or validator errors spike above 10%, the automated tripwire instantly disables the policy and reverts to safety.

---

## What `GH_` Stands For

> In all configuration files and environment variables, **`GH_` stands for `Gateway-Harness`**.

All configuration parameters in this project are strictly namespaced with the `GH_` prefix (e.g., `GH_DATABASE_URL`, `GH_ADMIN_TOKEN`, `GH_DAILY_OPTIMIZER_BUDGET_USD`).

### Why is this important?
1. **Namespace Isolation:** Prevents collisions with system-wide environment variables when running in Kubernetes, Docker Compose, or alongside existing applications.
2. **Predictable Settings Hierarchy:** The application loads settings via Pydantic (`pydantic-settings`). Any variable with the `GH_` prefix automatically overrides `.env` and defaults.

---

## Secrets & Credentials Guide

All credentials and environment variables are defined in `compose/.env.example`. Copy this file to `.env`:
```bash
cp compose/.env.example compose/.env
```

### 1. Internal Appliance Secrets (No 3rd-Party Vendor Needed)
These are secrets internal to the appliance. You can generate them immediately on your machine without signing up for any external services:

| Variable | Description | How to Generate / Source |
|---|---|---|
| `GH_ADMIN_TOKEN` | Bearer token securing the Admin REST API & Web Dashboard (`http://localhost:8000`) | Generate with OpenSSL:<br>`openssl rand -hex 20`<br>or PowerShell:<br>`-join ((65..90)+(97..122)+(48..57) \| Get-Random -Count 32 \| %{[char]$_})` |
| `LITELLM_MASTER_KEY` / `GH_INTERNAL_KEY` | Master API key used by clients and internal workers to authenticate with the proxy (`http://localhost:4000`) | Generate with OpenSSL:<br>`openssl rand -hex 24` |
| `POSTGRES_PASSWORD` | Password for the local PostgreSQL database container | Any secure alphanumeric string (e.g. `postgres`, `devpassword123`) |
| `GH_DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/gateway_harness` |
| `GH_DAILY_OPTIMIZER_BUDGET_USD` | Maximum dollar amount the probe engine is allowed to spend per day | Set to your daily limit (default: `20.0`) |

### 2. Third-Party Vendor API Keys (For Production Routing & Optimization)
When you want the proxy to route to real external foundation models or evaluate using frontier judges:

| Vendor | Environment Variable | Where to Obtain |
|---|---|---|
| **OpenAI** | `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Anthropic** | `ANTHROPIC_API_KEY` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| **Google Gemini** | `GEMINI_API_KEY` | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| **OpenRouter** | `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) |
| **Mistral AI** | `MISTRAL_API_KEY` | [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys) |

### 3. Zero-Spend / 100% Offline Test Mode (No Vendor Accounts Required!)
Gateway-Harness comes pre-configured with **mock model providers** in `config/litellm.yaml`:
- `spike-src`: Simulated expensive frontier model.
- `spike-dst`: Simulated cheap candidate model.

You can run the entire system, execute unit tests, evaluate prompt clustering, and test the full dashboard without providing any external API keys or spending a single cent.

---

## Running with Docker & Docker Compose

### Prerequisites
- Docker Engine 24.0+ and Docker Compose v2.20+

### Step-by-Step Launch

```bash
# 1. Clone or enter the repository
cd gateway-harness

# 2. Configure environment
cp compose/.env.example compose/.env

# 3. Start all services in background
docker compose -f compose/docker-compose.yml up -d
```

### Services Started:
- **`gateway` (Port `4000`):** The LLM proxy gateway (`http://localhost:4000`).
- **`admin` (Port `8000`):** The control dashboard and REST API (`http://localhost:8000`).
- **`worker`:** The background ingester, canary evaluator, and optimization scheduler.
- **`postgres` (Port `5432`):** Stores routing policies, proposals, audit logs, and tenant modes.

### Verifying Service Health:
```bash
# Check container status
docker compose -f compose/docker-compose.yml ps

# Inspect gateway logs
docker compose -f compose/docker-compose.yml logs -f gateway

# Query health probe
curl http://localhost:8000/health
# {"status":"healthy"}
```

---

## Running on Windows & WSL2

Gateway-Harness is fully supported on Windows. Depending on your workflow, choose between **Docker Desktop for Windows** (Recommended) or **WSL2 (Windows Subsystem for Linux)**.

### Option A: Docker Desktop for Windows (Recommended)

1. **Install Docker Desktop:**
   - Download and install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/).
   - Ensure the **WSL 2 based engine** option is enabled in Docker Desktop settings (*Settings > General > Use the WSL 2 based engine*).

2. **Crucial Windows Note: Git Line Endings (CRLF vs LF):**
   - Windows checkouts may convert Linux script line endings from `LF` to `CRLF`. This can cause `/bin/sh^M: bad interpreter` errors when running container entrypoints.
   - This repository includes a `.gitattributes` file that automatically forces `LF` endings for `.sh`, `.py`, `.sql`, and `Dockerfile`.
   - If cloning manually on Windows PowerShell, run:
     ```powershell
     git config --global core.autocrlf input
     git clone <repo-url>
     ```

3. **Start the Appliance in PowerShell:**
   ```powershell
   cd compose
   Copy-Item .env.example .env
   docker compose up -d
   ```

4. **Access the Endpoints:**
   - Gateway Proxy: `http://localhost:4000/v1`
   - Admin Dashboard: `http://localhost:8000/overview`

---

### Option B: Inside WSL2 (Ubuntu / Debian on Windows)

WSL2 provides a native Linux kernel inside Windows, ideal for local Python development without Docker overhead.

1. **Open your WSL2 terminal:**
   ```bash
   wsl -d Ubuntu
   ```

2. **Install `uv` (Fastest Python Package Manager):**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source ~/.cargo/env
   ```

3. **Clone and Install Dependencies:**
   ```bash
   git clone <repo-url> gateway-harness
   cd gateway-harness
   uv sync --extra dev
   ```

4. **Run the Full Test Suite:**
   ```bash
   uv run pytest -q
   # 139 passed
   ```

5. **WSL2 Networking Tip:**
   Modern WSL2 automatically mirrors ports to the Windows host. A service running on port `8000` or `4000` in WSL2 can be opened directly in Windows Chrome / Edge at `http://localhost:8000`.

---

## Meta Hackathon Demo Runbook

The appliance includes a built-in **Time-Compression Demo Track** designed specifically for live presentations. It fast-forwards 10 days of production traffic into 2 seconds and showcases the automated tripwire circuit breaker in action.

```bash
# 1. Fast-forward 10 days of simulated production data:
docker compose -f compose/docker-compose.yml exec admin gh demo --fast-forward

# 2. View the zero-LLM Savings Opportunity Report:
docker compose -f compose/docker-compose.yml exec admin gh report

# 3. Open the control center in your browser:
# Navigate to http://localhost:8000/overview

# 4. Trigger the Chaos Injection to showcase the automated circuit breaker:
# Simulates upstream model failure; tripwire auto-disables the policy in real-time
docker compose -f compose/docker-compose.yml exec admin gh demo --chaos pol_doc_extract

# 5. Emergency Kill Switch:
# Click the "EMERGENCY STOP" button in the dashboard header or call:
curl -X POST http://localhost:8000/api/kill -H "Content-Type: application/json" -d '{"enabled": true}'
```

---

## Developer & Testing Guide

### Local Environment Setup (macOS / Linux / WSL2)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync virtualenv and dependencies
uv sync --extra dev

# Run all unit and contract tests (139 tests)
uv run pytest -v

# Run linter and formatting checks
uv run ruff check .
uv run ruff format --check .
```

### Synthetic Traffic Generator (Evalharness)

Simulate 6 realistic production archetypes (classification, extraction, summarization, translation, Q&A RAG, and drafting):
```bash
python -m evalharness.run_eval
```

---

## Publishing as a Standalone Repository

To publish this standalone appliance to your own GitHub or GitLab account:

```bash
cd gateway-harness

# 1. Initialize git repository
git init -b main

# 2. Add all files
git add .

# 3. Commit the initial release
git commit -m "feat: initial release of Gateway-Harness appliance (P0-P10 complete)"

# 4. Link to your remote GitHub repository
git remote add origin https://github.com/<your-username-or-org>/gateway-harness.git

# 5. Push to GitHub
git push -u origin main
```

---

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

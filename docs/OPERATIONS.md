# Gateway-Harness Appliance: Operations Manual

## 1. Quick Start
Deploy with Docker Compose:
```bash
cd compose
cp .env.example .env
docker compose up -d
```

## 2. Emergency Kill Switch Runbook
If anomalous behavior is detected, immediately trip the global kill switch:
```bash
# Via Admin UI:
Click "EMERGENCY STOP" at http://localhost:8000/overview

# Or via REST API:
curl -X POST http://localhost:8000/api/kill -H "Content-Type: application/json" -d '{"enabled": true}'
```
All proxy traffic instantly reverts to 100% pass-through without dropping requests.

## 3. Meta Hackathon Demo Runbook
```bash
# 1. Fast-forward 10 days of production data (2 seconds):
docker compose exec admin gh demo --fast-forward

# 2. View identified clusters & savings:
docker compose exec admin gh report

# 3. Open dashboard at http://localhost:8000

# 4. Trigger chaos injection to demo the circuit breaker:
docker compose exec admin gh demo --chaos <policy_id>
```

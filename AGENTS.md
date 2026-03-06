# AGENTS.md

## Cursor Cloud specific instructions

### Overview
MemeCoin Scalper Bot — a Python 3.11 FastAPI application that scalps memecoins on Solana via Pump.fun. Single-process async architecture using uvicorn.

### Running the application
```bash
source /workspace/.venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```
The bot requires a `.env` file (copy from `.env.example`). For local dev/testing, set `DRY_RUN=true` and provide any valid Solana keypair as `WALLET_PRIVATE_KEY` (can be a dummy key generated with `solders.keypair.Keypair()`).

### Key endpoints
- `GET /health` — returns JSON health status (will show "degraded" if Redis is not running; this is normal for local dev)
- `GET /metrics` — Prometheus metrics stub (actual metrics served on port 9090)
- `POST /force-sell-all?dry_run=true` — emergency sell all tokens (supports dry_run param)

### Important caveats
- **Python 3.11 required**: The project uses `python:3.11-slim` in its Dockerfile. Python 3.12+ may work but is untested with `solders`/`solana`/`anchorpy` pinned versions.
- **Redis is optional**: Health shows "degraded" without Redis — this is expected and does not block the bot from running.
- **PostgreSQL is optional**: Without `DATABASE_URL`, positions are persisted to `data/positions.json`.
- **No test suite**: The project has no automated tests (unit/integration). Validation is done via dry-run mode and manual observation of logs/Telegram alerts.
- **No linter config**: No flake8/ruff/mypy configuration exists. Use `python -m py_compile <file>` for syntax checks.
- **WebSocket connection**: On startup the bot connects to PumpPortal WebSocket (`wss://pumpportal.fun/api/data`) and immediately starts receiving real-time token data. This is expected behavior even in DRY_RUN mode.
- **Prometheus metrics server**: Starts automatically on port 9090 during app startup.
- **Directories**: Ensure `logs/` and `data/` directories exist before starting.

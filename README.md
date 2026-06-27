# crafton-api

Backend API for **CRAFT-ON** — an on-demand "spot matching" platform for
construction tradespeople in Japan ("Timee for construction sites"). Phase 1 MVP.

Python + **FastAPI**, SQLAlchemy 2.0 + Alembic, PostgreSQL (Cloud SQL), Firebase
Auth (phone OTP). Hosted on Cloud Run in `asia-northeast1` (Tokyo).

> **The product/spec source of truth is the [`crafton`](../crafton) repo** —
> read its `docs/` first (start with `CLAUDE.md` and `docs/04-phase-1-spec.md`).
> This repo owns the **DB migrations** and the **authoritative OpenAPI** schema.

## Quickstart

```bash
# 1. Install (uv recommended)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Configure
cp .env.example .env

# 3. Database (local Postgres via docker)
docker compose up -d db
alembic upgrade head

# 4. Run
uvicorn app.main:app --reload
#   API:     http://localhost:8000/api/v1
#   Docs:    http://localhost:8000/docs        (OpenAPI — authoritative)
#   Health:  http://localhost:8000/healthz  /  /readyz
```

## Quality gates

```bash
ruff check .        # lint
mypy app            # type-check
pytest              # unit + integration tests
```

CI (GitHub Actions, `.github/workflows/ci.yml`) runs lint, type-check, the
**i18n ja/en parity check**, the test suite against a Postgres service, and an
Alembic **upgrade → downgrade** round-trip on every push/PR.

## Auth modes

`CRAFTON_AUTH_MODE` selects how `Authorization: Bearer <token>` is verified:

- `fake` (default for local/dev/tests) — no GCP needed; the token is a small
  JSON payload understood by the fake verifier. See `app/core/auth.py`.
- `firebase` — real Firebase ID-token verification (`pip install ".[firebase]"`,
  set `CRAFTON_FIREBASE_PROJECT_ID` and `GOOGLE_APPLICATION_CREDENTIALS`).

## Configuration

Every business limit (fees, area, caps, timings, flags) is configurable with
**permissive defaults**, never hardcoded. Precedence:

```
runtime app_config (DB)  >  CRAFTON_CFG__<KEY> env var  >  built-in default
```

Defaults and meanings are documented in `crafton/docs/07-config-and-flags.md` and
implemented in `app/core/config.py`.

## Layout

See `CLAUDE.md` for the directory map and contribution rules.

# CLAUDE.md — `crafton-api`

This is the **backend API** for CRAFT-ON. It is one of several repos. The
**source of truth for product, architecture, data model, API contract, config,
compliance, and testing lives in the `crafton` repo** (`docs/`). **Read those
docs first** — this file only pins the essentials and the API-local conventions.

> Golden rule: docs are the source of truth. If you change a decision, update the
> relevant `crafton/docs/` file in the same change. Code and docs must not drift.

## Read first (in the `crafton` repo)

- `CLAUDE.md` — project-wide rules.
- `docs/04-phase-1-spec.md` — what Phase 1 must do (build order in §7).
- `docs/05-data-model.md` — tables/columns (this repo owns the Alembic migrations).
- `docs/06-api-contract.md` — endpoint list (FastAPI's OpenAPI is authoritative).
- `docs/07-config-and-flags.md` — every tunable + defaults (never hardcode these).
- `docs/08-compliance-legal.md` — visa gate, contact masking, My Number rules.
- `docs/09-testing-strategy.md` — what must be tested.
- `docs/11-i18n.md` — ja default + full en, key parity enforced.

## Locked decisions (do not silently change — see `crafton/docs/adr/`)

| Area | Decision |
|---|---|
| Language/runtime | Python 3.11, **FastAPI** |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** (every schema change is a migration) |
| DB | **PostgreSQL** (Cloud SQL), `asia-northeast1` |
| Auth | **Firebase Auth** phone OTP; API verifies the Firebase ID token (Bearer), stateless |
| Money | integer **JPY**, never floats |
| Time | store **UTC**; business rules in **Asia/Tokyo** |
| IDs | **UUID v4** primary keys |
| i18n | message **keys are English**; default rendered locale **`ja`**, full **`en`** |
| Config | **runtime `app_config` override → env → built-in default**; permissive defaults |

The **one hard compliance gate in MVP** is foreign-worker visa validity. Keep
`contact_mask_enabled` and `visa_gate_enabled` ON.

## Layout

```
app/
  main.py            FastAPI app factory: middleware, routers, exception handlers
  core/
    config.py        Settings (env) + business-config registry + ConfigService (precedence)
    auth.py          Firebase token verification (real + fake) and current-user deps
    i18n.py          message catalog (ja/en) + translate()
    errors.py        AppError + JSON error envelope {error:{code,message}}
    logging.py       structured logging setup
  db/                SQLAlchemy engine/session/Base
  models/            ORM models (one module per table) + enums
  schemas/           Pydantic request/response models
  api/v1/            routers (system, auth, ... added per build order)
  locales/           ja.json / en.json backend message catalogs
migrations/          Alembic (env.py + versions/)
tests/               pytest (unit + integration)
```

## Conventions (API-local)

- **Never hardcode a value from `docs/07`** — read it through `ConfigService`.
- **Every user-facing string is a catalog key** (errors, notifications). Add it to
  **both** `app/locales/ja.json` and `app/locales/en.json` in the same change; CI
  fails on key drift.
- **Every schema change = an Alembic migration.** Never edit the DB by hand.
- **Tests are not optional.** Business rules in `docs/09` are the priority: contact
  masking, visa gate, freelance-insurance gate, matching state machine, fee
  recording, contract-type routing, config precedence, per-role authZ, i18n parity.
- Local dev & tests use **fake auth** (`CRAFTON_AUTH_MODE=fake`) and a local/CI
  Postgres — **no real GCP required**.
- Stateless: no server-side sessions; all state in Postgres / Storage.

## Dev quickstart

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env
docker compose up -d db          # local Postgres
alembic upgrade head             # apply migrations
uvicorn app.main:app --reload    # http://localhost:8000/docs

ruff check . && mypy app && pytest
```

## When you finish a unit of work

1. Run `ruff check . && mypy app && pytest` — all green.
2. If you changed the schema, add a migration and confirm `upgrade`/`downgrade`.
3. If you changed the API surface, update `crafton/docs/06-api-contract.md`.
4. Update `crafton/docs/STATUS.md`.
5. Commit with a clear message (what changed + why).

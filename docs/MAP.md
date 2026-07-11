# MAP.md — repo index for AI sessions

Per-module index of `crafton-api`. Product/architecture docs live in the
`crafton` repo (`docs/`); dev quickstart is in this repo's `CLAUDE.md`.

## Modules

| Module | Purpose |
|---|---|
| `app/main.py` | App factory: CORS, error handlers, mounts system router + `/api/v1` |
| `app/core/config.py` | Env `Settings` + business-config registry + `ConfigService` (app_config row > `CRAFTON_CFG__*` env > default) |
| `app/core/auth.py` | OTP token verification: `FirebaseTokenVerifier` / `FakeTokenVerifier` (`CRAFTON_AUTH_MODE`), `FirebaseClaims` |
| `app/core/session_token.py` | App-issued HS256 session JWTs (issue/verify, stdlib only) |
| `app/core/security.py` | Password hashing (PBKDF2-HMAC-SHA256, stdlib) |
| `app/core/identifiers.py` | Username/email/phone normalization for login identifiers |
| `app/core/i18n.py` | ja/en catalog + `translate()` + `resolve_locale()`; `python -m app.core.i18n --check` = parity check |
| `app/core/errors.py` | `AppError` + factories; exception handlers render `{error:{code,message}}` localized via `request.state.locale` |
| `app/core/clock.py` | UTC storage / Asia/Tokyo business time (`tokyo_today`), monkeypatchable |
| `app/core/logging.py` | Structured JSON logging for Cloud Logging |
| `app/core/storage.py` | `StorageService` signed upload/read URLs: `GcsStorage` / `FakeStorage` (`CRAFTON_STORAGE_MODE`) |
| `app/db/base.py` | Declarative `Base`, naming convention, UUID/timestamp mixins |
| `app/db/session.py` | Engine, session factory, `get_db` dependency (sync sessions) |
| `app/models/` | ORM, one module per table: user, worker_profile, contractor_profile, document, job, application, matching, message, review, notification, saved_job, device, trade, app_config; `enums.py` = shared StrEnums |
| `app/schemas/` | Pydantic request/response models, roughly one module per domain; `common.py` = error envelope + shared `RESP_*` responses maps |
| `app/api/deps.py` | Auth deps: `get_claims` → `get_current_user` → role/approval guards (`approved_worker`, `admin_user`, …), `get_config`, `get_storage_service` |
| `app/api/system.py` | `/healthz`, `/readyz` (root, no auth) |
| `app/api/v1/router.py` | Aggregates all v1 feature routers |
| `app/services/onboarding.py` | Profile create/update services + `worker_out`/`contractor_out` DTO builders |
| `app/services/documents.py` | Signed upload URLs, register, list, view documents |
| `app/services/jobs.py` | Job post/search/lifecycle; config-driven area/trade checks |
| `app/services/saved_jobs.py` | Worker job bookmarks (idempotent save/unsave) |
| `app/services/applications.py` | Apply + **confirm**: compliance gates, contract-type routing, wage snapshot, fee recording |
| `app/services/matchings.py` | Matching reads, participant authZ, `enrich_matching` DTO enrichment |
| `app/services/lifecycle.py` | Day-of transitions: check-in → complete-request → approve-completion, cancel |
| `app/services/state_machine.py` | Legal matching-status transitions (single authority) |
| `app/services/compliance.py` | Visa gate + freelance-insurance gate (config-toggleable, ON by default) |
| `app/services/masking.py` | Authoritative contact masking for chat (anti-中抜き) |
| `app/services/chat.py` | Message list/send (send applies masking) |
| `app/services/reviews.py` | Two-way post-completion reviews; recompute trust_score/rating |
| `app/services/notifications.py` | Create-on-event (commit with caller), list, mark read |
| `app/services/devices.py` | Device touch/list/revoke (via `X-Device-Id` header) |
| `app/services/trades.py` | Trade catalog CRUD + free-text merge |
| `app/services/vetting.py` | Admin approve/reject/suspend (+ auto-approve), enforces visa gate |
| `app/services/admin_ops.py` | Admin matchings overview, fee reconciliation, config overrides, create admin |
| `app/services/terms.py` | Localized human-readable contract terms (placeholder wording) |
| `app/services/debug_seed.py` | Random dev/CI seed data (fake-auth only) |
| `app/locales/{ja,en}.json` | Backend message catalogs (key parity enforced) |
| `migrations/versions/` | Alembic migrations (this repo owns the schema) |

## Router → endpoints (all under `/api/v1`)

| Router | Endpoints |
|---|---|
| `auth.py` | POST `/auth/session` (register/return, OTP token), `/auth/password`, `/auth/login`, `/auth/reset-password`; PATCH `/me/account`; GET `/me` |
| `onboarding.py` | POST `/onboarding/{worker,contractor}`; PATCH `/workers/me`, `/contractors/me`; GET `/workers/{id}`, `/contractors/{id}` |
| `documents.py` | POST `/documents/upload-url`, `/documents`; GET `/documents/me`, `/documents/{id}/view-url`, `/workers/{id}/photos` |
| `jobs.py` | POST `/jobs`, `/jobs/{id}/cancel`; GET `/jobs`, `/jobs/mine`, `/jobs/saved`, `/jobs/saved-ids`, `/jobs/{id}`, `/jobs/{id}/photos`; PATCH `/jobs/{id}`; PUT/DELETE `/jobs/{id}/save` |
| `matching.py` | POST `/jobs/{id}/apply`, `/applications/{id}/{confirm,reject,withdraw}`, `/matchings/{id}/{check-in,complete-request,approve-completion,cancel}`; GET `/jobs/{id}/applications`, `/applications/mine`, `/matchings/mine`, `/matchings/history`, `/matchings/{id}` |
| `chat.py` | GET/POST `/matchings/{id}/messages` |
| `reviews.py` | POST `/matchings/{id}/reviews`; GET `/workers/{id}/reviews`, `/contractors/{id}/reviews` |
| `notifications.py` | GET `/notifications`, `/notifications/unread-count`; POST `/notifications/read-all`, `/notifications/{id}/read` |
| `devices.py` | GET `/me/devices`, `/admin/devices`; POST `/me/devices/{id}/revoke` |
| `trades.py` | GET `/trades`, `/admin/trades`, `/admin/trades/custom`; POST `/admin/trades`, `/admin/trades/merge`; PATCH `/admin/trades/{id}` |
| `admin.py` | GET `/admin/vetting/queue`, `/admin/users`, `/admin/jobs`, `/admin/admins`, `/admin/matchings`, `/admin/config`; POST `/admin/admins`, `/admin/users/{id}/{approve,reject,suspend}`, `/admin/matchings/{id}/mark-fee-paid`, `/admin/debug/seed`; PATCH `/admin/config` |

## Where to change what

| Change | Files |
|---|---|
| Add endpoint | `app/api/v1/<feature>.py` (+ register in `router.py` if new module), logic in `app/services/`, schemas in `app/schemas/`, tests; update `crafton/docs/06-api-contract.md` |
| Add table / column | `app/models/<table>.py` (+ import in `models/__init__.py`), Alembic migration in `migrations/versions/`, schemas, `tests/conftest.py` `_ALL_TABLES` |
| Add config var / feature flag | Registry in `app/core/config.py` (`BUSINESS_CONFIG_DEFAULTS` / `FEATURE_FLAG_DEFAULTS`), read via `ConfigService`; document in `crafton/docs/07-config-and-flags.md` |
| Add user-facing string | Key in **both** `app/locales/ja.json` and `en.json` (parity CI-enforced); render via `core.i18n.translate` / `errors.AppError` |
| Add notification type | `services/notifications.py` call site + `notification.<type>.{title,body}` keys in both locale files (`tests/test_notifications.py`) |
| Change compliance gate | `app/services/compliance.py` (+ `vetting.py` for approval-time checks); re-read `crafton/docs/08`; tests `test_vetting_visa_gate.py`, `test_matching.py` |
| Change matching state flow | `app/services/state_machine.py` + `lifecycle.py`; tests `test_state_machine.py`, `test_lifecycle.py` |
| Add authZ guard | `app/api/deps.py` (compose over `get_current_user`/`require_active`) |
| Documented error statuses | Shared `RESP_404`/`RESP_403_404`/`RESP_403_404_409` in `app/schemas/common.py` |

## Tests

`tests/` — pytest against a real local Postgres (fake auth, tables truncated per test).
- `conftest.py`: `engine`/`db`/`client` fixtures, `auth_headers`, `approved_member`, `seed_admin`.
- `factories.py`: shared payloads (`CONTRACTOR`, `WORKER`, `JOB`, `signup_payload`), `unique_phone`, and the `post_job` → `apply_to_job` → `confirm_matching`/`confirmed_matching` → `complete_matching` chain helpers.
- Unit-level files (no HTTP client): `test_masking.py`, `test_state_machine.py`, `test_i18n_parity.py`, `test_session_token.py`, `test_config_precedence.py` (DB only).
- The rest are endpoint/integration tests, one file per feature (`test_jobs.py`, `test_matching.py`, `test_lifecycle.py`, …).

Dev quickstart: see `CLAUDE.md` (uv venv, docker compose Postgres, alembic, uvicorn; gates: `ruff check . && mypy app && pytest`).

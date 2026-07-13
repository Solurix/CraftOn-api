"""Application configuration & the business-config / feature-flag layer.

Two distinct concerns live here:

1. **Settings** — infrastructure/app-level configuration sourced from the
   environment (DB URL, auth mode, log level, …). These are read once at
   startup and don't change at runtime.

2. **Business config & feature flags** — the tunables documented in
   ``crafton/docs/07-config-and-flags.md`` (fees, service area, caps, timings,
   flags). These follow the project rule: *start permissive, make everything a
   variable, never hardcode.* They are resolved through :class:`ConfigService`
   with the precedence:

       runtime ``app_config`` row  >  ``CRAFTON_CFG__<KEY>`` env var  >  default

   Keeping the defaults in one registry here (mirroring docs/07) means a future
   session can't accidentally hardcode a limit somewhere in the codebase.
"""

from __future__ import annotations

import json
import os
from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class AppEnv(StrEnum):
    LOCAL = "local"
    CI = "ci"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class AuthMode(StrEnum):
    FAKE = "fake"
    FIREBASE = "firebase"


class StorageMode(StrEnum):
    FAKE = "fake"
    GCS = "gcs"


class Settings(BaseSettings):
    """Infrastructure/app-level settings sourced from the environment.

    All keys are prefixed ``CRAFTON_`` (see ``.env.example``).
    """

    model_config = SettingsConfigDict(
        env_prefix="CRAFTON_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: AppEnv = AppEnv.LOCAL
    debug: bool = True
    log_level: str = "INFO"

    # Database
    database_url: str = (
        "postgresql+psycopg://crafton:crafton@localhost:5432/crafton"
    )
    # Preview environments: when ``CRAFTON_DB_NAME`` is set we swap ONLY the
    # db-name path segment of ``database_url`` (see ``effective_database_url``).
    # This lets a per-PR preview point at its own isolated database while still
    # mounting the shared ``crafton-db-url`` secret — the password/socket never
    # leave Secret Manager and no second secret is needed. Unset in dev/CI/tests.
    db_name: str | None = None

    # Auth
    auth_mode: AuthMode = AuthMode.FAKE
    firebase_project_id: str = "crafton-dev-500709"
    # App-issued session tokens (identifier+password login). The secret signs the
    # HS256 JWT; the dev default keeps local/CI working with no setup, but a real
    # secret MUST be supplied via env/Secret Manager in staging/prod.
    session_secret: str = "dev-insecure-session-secret-change-me"
    session_ttl_seconds: int = 7 * 24 * 3600  # 7 days

    # Cloud Storage (documents). `fake` returns deterministic local URLs for
    # dev/CI/tests; `gcs` issues real signed URLs (requires the `gcs` extra).
    storage_mode: StorageMode = StorageMode.FAKE
    gcs_bucket: str = "crafton-dev-500709-uploads"
    signed_url_ttl_seconds: int = 900

    # i18n
    default_language: str = "ja"
    supported_languages: list[str] = Field(default_factory=lambda: ["ja", "en"])

    @field_validator("supported_languages", mode="before")
    @classmethod
    def _split_languages(cls, v: Any) -> Any:
        # Allow "ja,en" in addition to JSON '["ja","en"]'.
        if isinstance(v, str) and not v.strip().startswith("["):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def is_testing(self) -> bool:
        return self.env in (AppEnv.CI, AppEnv.LOCAL)

    @property
    def effective_database_url(self) -> str:
        """``database_url`` with the db-name segment swapped for ``db_name``.

        Returns ``database_url`` unchanged when ``db_name`` is unset (dev/CI/prod).
        Handles both URL shapes we deploy with:

        * Cloud SQL unix socket — ``postgresql+psycopg://user:pw@/crafton?host=/cloudsql/PROJ:REGION:INST``
        * host:port — ``postgresql+psycopg://user:pw@host:5432/crafton``

        Only the ``<db>`` name changes; credentials, socket/host and query string
        are preserved.
        """
        if not self.db_name:
            return self.database_url
        head, sep_at, rest = self.database_url.partition("@/")  # Cloud SQL socket form
        if not sep_at:  # host:port/db fallback
            base, _, tail = self.database_url.rpartition("/")
            _old, q_sep, query = tail.partition("?")
            return f"{base}/{self.db_name}{q_sep}{query}"
        _old, q_sep, query = rest.partition("?")
        return f"{head}@/{self.db_name}{q_sep}{query}"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton (cleared in tests via ``get_settings.cache_clear``)."""
    return Settings()


# ---------------------------------------------------------------------------
# Business config & feature-flag registry (mirrors crafton/docs/07).
#
# IMPORTANT: do not hardcode any of these values elsewhere — read them through
# ConfigService. When adding a tunable, add it here AND to docs/07 in the same
# change. Defaults are permissive unless the key is a compliance gate
# (contact_mask_enabled, visa_gate_enabled, require_freelance_insurance).
# ---------------------------------------------------------------------------

BUSINESS_CONFIG_DEFAULTS: dict[str, Any] = {
    "service_area_prefectures": ["Tokyo", "Kanagawa", "Saitama", "Chiba"],
    "service_area_enforce": False,
    "allowed_trades": [],  # empty = any trade allowed
    "platform_fee_per_match": 3000,  # JPY, Phase 1 flat fee
    "commission_rate": 0.15,  # (P2)
    "worker_management_fee_monthly": 220,  # (P2)
    "subscription_management_monthly": 29800,  # (P3)
    "spot_plan_commission_rate": 0.25,  # (P3)
    "withholding_threshold_jpy": 9300,  # (P2)
    "noshow_confirm_hour_local": 20,  # Asia/Tokyo
    "noshow_morning_lead_minutes": 120,  # (P2)
    "job_edit_cutoff_hours": 12,  # edits blocked within N h of start (Asia/Tokyo); 0 = off
    "checkin_open_minutes_before_start": 120,  # check-in opens N min before start; <=0 = off
    "checkin_radius_meters": 500,  # (GPS verify P2)
    "weekly_work_hours_cap": None,  # null = no cap (permissive)
    "student_visa_weekly_hours": 28,  # (P2)
    "require_freelance_insurance": True,  # compliance-ish gate (toggleable)
    "penalty_thresholds": {"warn": 1, "restrict": 2, "ban": 3},  # (P2)
    "default_language": "ja",
    "supported_languages": ["ja", "en"],
}

FEATURE_FLAG_DEFAULTS: dict[str, bool] = {
    "payments_enabled": False,  # (P2)
    "withholding_enabled": False,  # (P2)
    "factoring_enabled": False,  # (P2)
    "insurance_autoattach_enabled": False,  # (P2)
    "ekyc_enabled": False,  # (P2)
    "auto_checkin_enabled": False,  # (P2)
    "auto_penalties_enabled": False,  # (P2)
    "translation_enabled": False,  # (P3)
    "ai_instruction_sheets_enabled": False,  # (P3)
    "greensite_export_enabled": False,  # (P3)
    "subscriptions_enabled": False,  # (P3)
    "supervisor_matching_enabled": False,  # (P3)
    "waitlist_out_of_area": True,
    "contact_mask_enabled": True,  # keep ON — core anti-中抜き value
    "visa_gate_enabled": True,  # keep ON — legal gate
    # When ON, a user is approved automatically as soon as they finish onboarding
    # (still subject to the visa/insurance gate), so no manual admin vetting is
    # needed. Default OFF — manual vetting. Convenient for dev/testing.
    "auto_approve_users": False,
}

# Combined registry of every runtime-resolvable key.
CONFIG_DEFAULTS: dict[str, Any] = {**BUSINESS_CONFIG_DEFAULTS, **FEATURE_FLAG_DEFAULTS}

_ENV_OVERRIDE_PREFIX = "CRAFTON_CFG__"


def _env_override(key: str) -> tuple[bool, Any]:
    """Return ``(found, value)`` for a ``CRAFTON_CFG__<KEY>`` env override.

    The value is JSON-decoded so types (ints, bools, lists) survive; if it isn't
    valid JSON it is treated as a raw string.
    """
    raw = os.environ.get(f"{_ENV_OVERRIDE_PREFIX}{key.upper()}")
    if raw is None:
        return False, None
    try:
        return True, json.loads(raw)
    except json.JSONDecodeError:
        return True, raw


class ConfigService:
    """Resolves business config / flags with documented precedence.

    Precedence (highest first):
        1. runtime ``app_config`` row (admin override)
        2. ``CRAFTON_CFG__<KEY>`` environment variable
        3. built-in default from :data:`CONFIG_DEFAULTS`

    Pass a SQLAlchemy ``Session`` to enable layer (1). Without a session only
    env + defaults are consulted (useful for pure-unit use).
    """

    def __init__(self, db: Session | None = None) -> None:
        self._db = db

    # -- core resolution ----------------------------------------------------

    def get(self, key: str) -> Any:
        if key not in CONFIG_DEFAULTS:
            raise KeyError(f"Unknown config key: {key!r}. Add it to CONFIG_DEFAULTS and docs/07.")

        # 1. runtime override (app_config table)
        if self._db is not None:
            override = self._db_override(key)
            if override is not _MISSING:
                return override

        # 2. environment override
        found, value = _env_override(key)
        if found:
            return value

        # 3. built-in default
        return CONFIG_DEFAULTS[key]

    def _db_override(self, key: str) -> Any:
        db = self._db
        if db is None:
            return _MISSING
        # Imported lazily to avoid a hard import cycle and to keep this module
        # importable without the ORM (e.g. in pure-logic unit tests).
        from app.models.app_config import AppConfig

        row = db.get(AppConfig, key)
        if row is None:
            return _MISSING
        return row.value

    # -- typed accessors ----------------------------------------------------

    def get_int(self, key: str) -> int:
        return int(self.get(key))

    def get_bool(self, key: str) -> bool:
        """Read a boolean, parsing common string/number spellings.

        Admin overrides and env vars can deliver ``"false"``/``"0"``/… as
        strings; plain ``bool()`` would treat any non-empty string as True.
        """
        value = self.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("false", "0", "no", "off"):
                return False
            if lowered in ("true", "1", "yes", "on"):
                return True
            return bool(value)  # unknown spelling — fall back to truthiness
        if isinstance(value, (int, float)):
            return value != 0
        return bool(value)

    def get_str(self, key: str) -> str:
        return str(self.get(key))

    def get_list(self, key: str) -> list[Any]:
        value = self.get(key)
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError(f"Config key {key!r} is not a list: {value!r}")
        return value

    def flag(self, key: str) -> bool:
        """Read a feature flag (bool)."""
        if key not in FEATURE_FLAG_DEFAULTS:
            raise KeyError(f"Unknown feature flag: {key!r}")
        return self.get_bool(key)

    def all_config(self) -> dict[str, Any]:
        """Resolved snapshot of every key (for the admin config endpoint)."""
        return {key: self.get(key) for key in CONFIG_DEFAULTS}


_MISSING: Any = object()

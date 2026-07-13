"""Config precedence: runtime app_config override > env var > built-in default.

This is a must-test business rule (docs/09): no business limit may be hardcoded,
and admin runtime overrides must win.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import CONFIG_DEFAULTS, ConfigService
from app.models.app_config import AppConfig

KEY = "platform_fee_per_match"
ENV_VAR = "CRAFTON_CFG__PLATFORM_FEE_PER_MATCH"


def test_returns_builtin_default(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert ConfigService(db).get(KEY) == CONFIG_DEFAULTS[KEY] == 3000


def test_env_var_overrides_default(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "5000")
    assert ConfigService(db).get_int(KEY) == 5000


def test_app_config_row_overrides_env(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "5000")
    db.add(AppConfig(key=KEY, value=7000))
    db.commit()
    assert ConfigService(db).get_int(KEY) == 7000


def test_unknown_key_raises(db: Session) -> None:
    with pytest.raises(KeyError):
        ConfigService(db).get("not_a_real_key")


def test_compliance_flags_default_on(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRAFTON_CFG__CONTACT_MASK_ENABLED", raising=False)
    monkeypatch.delenv("CRAFTON_CFG__VISA_GATE_ENABLED", raising=False)
    cfg = ConfigService(db)
    assert cfg.flag("contact_mask_enabled") is True
    assert cfg.flag("visa_gate_enabled") is True


def test_list_and_typed_accessors(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRAFTON_CFG__SERVICE_AREA_PREFECTURES", raising=False)
    cfg = ConfigService(db)
    assert cfg.get_list("service_area_prefectures") == [
        "Tokyo",
        "Kanagawa",
        "Saitama",
        "Chiba",
    ]
    # JSON-encoded list via env override survives typing.
    monkeypatch.setenv("CRAFTON_CFG__SERVICE_AREA_PREFECTURES", '["Tokyo"]')
    assert ConfigService(db).get_list("service_area_prefectures") == ["Tokyo"]


def test_all_config_snapshot_includes_every_key(db: Session) -> None:
    snapshot = ConfigService(db).all_config()
    assert set(snapshot) == set(CONFIG_DEFAULTS)


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (True, True),
        (False, False),
        ("false", False),  # the footgun: bool("false") is True
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("true", True),
        ("1", True),
        ("yes", True),
        ("ON", True),
        (0, False),
        (1, True),
        (2, True),
        ("", False),  # unknown strings fall back to truthiness
        ("maybe", True),
        (None, False),
    ],
)
def test_get_bool_parses_common_spellings(
    db: Session, stored: object, expected: bool
) -> None:
    """Admin config JSON can store booleans as strings — parse, don't truthify."""
    db.add(AppConfig(key="visa_gate_enabled", value=stored))
    db.commit()
    assert ConfigService(db).get_bool("visa_gate_enabled") is expected

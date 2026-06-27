"""i18n: ja/en catalogs must have identical key sets and no empty values.

Must-test rule (docs/09, docs/11). The same check runs standalone in CI.
"""

from __future__ import annotations

from app.core.i18n import check_parity, resolve_locale, translate


def test_ja_en_key_parity() -> None:
    problems = check_parity()
    assert problems == [], "i18n parity problems:\n" + "\n".join(problems)


def test_translate_renders_locale() -> None:
    assert translate("error.unauthorized", "en") == "Authentication required."
    assert translate("error.unauthorized", "ja") == "認証が必要です。"


def test_translate_falls_back_to_default_locale_then_key() -> None:
    # Unknown locale falls back to ja.
    assert translate("error.unauthorized", "fr") == "認証が必要です。"
    # Unknown key falls back to the key itself.
    assert translate("no.such.key", "en") == "no.such.key"


def test_translate_interpolates_params() -> None:
    # role.* keys exist in both catalogs; interpolation is a no-op here but must not raise.
    assert translate("role.worker", "en") == "Worker"


def test_resolve_locale_precedence() -> None:
    assert resolve_locale(None, "en") == "en"  # explicit preference wins
    assert resolve_locale("en-US,en;q=0.9", None) == "en"  # Accept-Language
    assert resolve_locale("fr-FR", None) == "ja"  # unsupported → default
    assert resolve_locale(None, None) == "ja"  # nothing → default

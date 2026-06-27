"""Backend message catalog (ja default + full en).

User-facing strings produced by the API (error messages, notification/SMS/email
templates, generated terms-document copy) are **keyed**, never hardcoded. Keys
are English; the default rendered locale is Japanese (``ja``). A complete English
(``en``) catalog with 100% key parity ships in Phase 1 and is enforced in CI.

See ``crafton/docs/11-i18n.md``.

Run the parity check standalone (used by CI):

    python -m app.core.i18n --check
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LOCALE = "ja"
SUPPORTED_LOCALES: tuple[str, ...] = ("ja", "en")
_LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


def _load_catalog(locale: str) -> dict[str, str]:
    path = _LOCALES_DIR / f"{locale}.json"
    with path.open(encoding="utf-8") as fh:
        data: dict[str, str] = json.load(fh)
    return data


class Catalog:
    """Loads per-locale message catalogs and renders keyed strings."""

    def __init__(self, locales: tuple[str, ...] = ("ja", "en")) -> None:
        self._catalogs: dict[str, dict[str, str]] = {
            loc: _load_catalog(loc) for loc in locales
        }

    @property
    def locales(self) -> list[str]:
        return list(self._catalogs)

    def translate(self, key: str, locale: str | None = None, /, **params: Any) -> str:
        """Render ``key`` in ``locale`` (falling back to ``ja`` then the key).

        ``params`` are substituted with ``str.format`` (``{name}`` placeholders).
        """
        locale = locale if locale in self._catalogs else DEFAULT_LOCALE
        template = self._catalogs[locale].get(key)
        if template is None:
            # Fall back to the source-of-truth locale, then the raw key.
            template = self._catalogs[DEFAULT_LOCALE].get(key, key)
        if params:
            try:
                return template.format(**params)
            except (KeyError, IndexError):
                return template
        return template


@lru_cache
def get_catalog() -> Catalog:
    """Cached catalog singleton for the running app."""
    return Catalog(SUPPORTED_LOCALES)


def resolve_locale(
    accept_language: str | None = None, preferred: str | None = None
) -> str:
    """Pick a supported locale: explicit preference > Accept-Language > ``ja``.

    Only the first language tag of Accept-Language is considered (good enough for
    a two-locale app); region subtags (``en-US``) are reduced to the base.
    """
    if preferred and preferred in SUPPORTED_LOCALES:
        return preferred
    if accept_language:
        for part in accept_language.split(","):
            tag = part.split(";")[0].strip().lower()
            base = tag.split("-")[0]
            if base in SUPPORTED_LOCALES:
                return base
    return DEFAULT_LOCALE


def translate(key: str, locale: str | None = None, /, **params: Any) -> str:
    """Module-level convenience over the cached catalog."""
    return get_catalog().translate(key, locale, **params)


def check_parity(locales: tuple[str, ...] = ("ja", "en")) -> list[str]:
    """Return a list of human-readable parity problems (empty == OK).

    Problems detected:
      * a key present in one locale but missing in another, and
      * an empty/whitespace-only value for any key.
    """
    catalogs = {loc: _load_catalog(loc) for loc in locales}
    key_sets = {loc: set(cat) for loc, cat in catalogs.items()}
    union = set().union(*key_sets.values())

    problems: list[str] = []
    for loc in locales:
        missing = union - key_sets[loc]
        for key in sorted(missing):
            problems.append(f"[{loc}] missing key: {key}")
        for key, value in catalogs[loc].items():
            if not str(value).strip():
                problems.append(f"[{loc}] empty value for key: {key}")
    return problems


def _main(argv: list[str]) -> int:
    if "--check" in argv:
        problems = check_parity()
        if problems:
            print("i18n parity check FAILED:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print("i18n parity check OK (ja/en key sets match, no empty values).")
        return 0
    print("usage: python -m app.core.i18n --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

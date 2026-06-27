"""Server-side contact masking — anti-disintermediation (中抜き) core value.

Authoritative filter applied to every outgoing chat message (docs/08). It masks
contact information so parties cannot move off-platform:

* phone numbers / any run of **10+ digits** (handles spaces, hyphens, full-width
  digits, and parentheses),
* email addresses (half- or full-width ``@``),
* keywords: ``LINE`` (any case, kana ライン/らいん, full-width ＬＩＮＥ), ``TEL``,
  and 電話.

Detected spans are replaced with a mask and ``was_filtered`` is set so the write
is audited and the client can warn. The filter is config-gated
(``contact_mask_enabled``, ON by default).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MASK = "●●●"

# Email: local@domain.tld, allowing a full-width ＠.
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+[@＠][A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# A run that starts and ends with a digit (\d also matches full-width digits),
# spanning digits + common separators. We then keep only runs with >=10 digits.
_SEPARATORS = r"\s\-‐‒–—―－−ー.　()（）"
_DIGIT_RUN = re.compile(rf"\d[\d{_SEPARATORS}]*\d")

# Off-platform contact keywords. ASCII keywords use letter-lookarounds (not \b,
# which fails against adjacent Japanese) so "LINEで" matches while English
# "deadline"/"online"/"hotel" do not. The katakana ライン is guarded against the
# common compound オンライン (online).
_KEYWORDS = re.compile(
    r"(?<![A-Za-z])LINE(?![A-Za-z])"
    r"|(?<![A-Za-z])TEL(?![A-Za-z])"
    r"|(?<!オン)ライン"
    r"|らいん"
    r"|ＬＩＮＥ"
    r"|ＴＥＬ"
    r"|電話",
    re.IGNORECASE,
)

_DIGIT_THRESHOLD = 10


@dataclass(frozen=True)
class MaskResult:
    text: str
    was_filtered: bool


def _mask_digit_runs(text: str, state: dict[str, bool]) -> str:
    def repl(match: re.Match[str]) -> str:
        run = match.group()
        if sum(1 for ch in run if ch.isdigit()) >= _DIGIT_THRESHOLD:
            state["filtered"] = True
            return MASK
        return run

    return _DIGIT_RUN.sub(repl, text)


def _mask_pattern(pattern: re.Pattern[str], text: str, state: dict[str, bool]) -> str:
    def repl(_match: re.Match[str]) -> str:
        state["filtered"] = True
        return MASK

    return pattern.sub(repl, text)


def mask_contact_info(text: str) -> MaskResult:
    """Return the masked text and whether anything was filtered."""
    state = {"filtered": False}
    # Order matters: emails first (they contain digits), then digit runs, then keywords.
    out = _mask_pattern(_EMAIL, text, state)
    out = _mask_digit_runs(out, state)
    out = _mask_pattern(_KEYWORDS, out, state)
    return MaskResult(text=out, was_filtered=state["filtered"])

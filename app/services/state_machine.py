"""Matching state machine — only legal transitions are allowed (docs/09).

    confirmed  → checked_in | canceled | noshow
    checked_in → completed  | canceled | noshow
    completed / canceled / noshow are terminal.

``complete-request`` (worker marks work done) does not change the status; it
records ``completion_requested_at`` while the matching stays ``checked_in`` until
the contractor approves (→ completed). See docs/04 §3.5.
"""

from __future__ import annotations

from app.core import errors
from app.models.enums import MatchingStatus

LEGAL_TRANSITIONS: dict[MatchingStatus, frozenset[MatchingStatus]] = {
    MatchingStatus.CONFIRMED: frozenset(
        {MatchingStatus.CHECKED_IN, MatchingStatus.CANCELED, MatchingStatus.NOSHOW}
    ),
    MatchingStatus.CHECKED_IN: frozenset(
        {MatchingStatus.COMPLETED, MatchingStatus.CANCELED, MatchingStatus.NOSHOW}
    ),
    MatchingStatus.COMPLETED: frozenset(),
    MatchingStatus.CANCELED: frozenset(),
    MatchingStatus.NOSHOW: frozenset(),
}


def can_transition(current: MatchingStatus, target: MatchingStatus) -> bool:
    return target in LEGAL_TRANSITIONS.get(current, frozenset())


def assert_transition(current: MatchingStatus, target: MatchingStatus) -> None:
    """Raise a 409 if ``current → target`` is not a legal transition."""
    if not can_transition(current, target):
        raise errors.AppError(
            code="illegal_matching_transition",
            status_code=409,
            message_key="error.matching.illegal_transition",
            params={"current": current.value, "target": target.value},
        )

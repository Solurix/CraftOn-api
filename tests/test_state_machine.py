"""Matching state-machine unit tests (must-test: only legal transitions)."""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.models.enums import MatchingStatus as S
from app.services.state_machine import assert_transition, can_transition

LEGAL = [
    (S.CONFIRMED, S.CHECKED_IN),
    (S.CONFIRMED, S.CANCELED),
    (S.CONFIRMED, S.NOSHOW),
    (S.CHECKED_IN, S.COMPLETED),
    (S.CHECKED_IN, S.CANCELED),
    (S.CHECKED_IN, S.NOSHOW),
]

ILLEGAL = [
    (S.CONFIRMED, S.COMPLETED),  # cannot complete without checking in
    (S.COMPLETED, S.CHECKED_IN),  # terminal
    (S.COMPLETED, S.CANCELED),  # terminal
    (S.CANCELED, S.CONFIRMED),  # terminal
    (S.NOSHOW, S.CHECKED_IN),  # terminal
    (S.CHECKED_IN, S.CONFIRMED),  # no going back
]


@pytest.mark.parametrize(("current", "target"), LEGAL)
def test_legal_transitions(current: S, target: S) -> None:
    assert can_transition(current, target)
    assert_transition(current, target)  # does not raise


@pytest.mark.parametrize(("current", "target"), ILLEGAL)
def test_illegal_transitions(current: S, target: S) -> None:
    assert not can_transition(current, target)
    with pytest.raises(AppError) as exc:
        assert_transition(current, target)
    assert exc.value.code == "illegal_matching_transition"
    assert exc.value.status_code == 409

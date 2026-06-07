"""Tests for the deferred per-user range override scaffolding (Requirement 8).

The `/range` command is intentionally NOT shipped yet; this only verifies the
data model reserves the field and that `neighbors`/`count_nearby` honor
`min(override, configured)` when an override is present.
"""

from __future__ import annotations

from tchaka.core import count_nearby
from tchaka.state import AppState, Coord, UserRecord


def _state_two_users() -> AppState:
    state = AppState()
    state.register(UserRecord("me", 1, Coord(52.5200, 13.4050), 0.0))
    # ~13 m away
    state.register(UserRecord("near", 2, Coord(52.5201, 13.4051), 0.0))
    # ~7.78 km away (beyond the default 5 km radius)
    state.register(UserRecord("midrange", 3, Coord(52.5900, 13.4050), 0.0))
    return state


def test_range_field_defaults_to_none() -> None:
    rec = UserRecord("u", 1, Coord(0.0, 0.0), 0.0)
    assert rec.range_km is None


def test_override_narrows_neighborhood() -> None:
    state = _state_two_users()
    # global threshold 10 km would include both near (~13m) and midrange (~7.9km)
    assert count_nearby(state, "me", threshold_km=10.0) == 2
    # set a tight 1 km override on "me" -> only the ~13m neighbor remains
    state.users["me"].range_km = 1.0
    assert count_nearby(state, "me", threshold_km=10.0) == 1


def test_override_capped_by_global() -> None:
    state = _state_two_users()
    # override larger than global must NOT widen beyond the global cap
    state.users["me"].range_km = 100.0
    # global 1 km -> only the ~13m neighbor, midrange (~7.9km) excluded
    assert count_nearby(state, "me", threshold_km=1.0) == 1


def test_effective_range_helper() -> None:
    state = AppState()
    rec = UserRecord("u", 1, Coord(0.0, 0.0), 0.0)
    assert state.effective_range(rec, 5.0) == 5.0  # no override
    rec.range_km = 2.0
    assert state.effective_range(rec, 5.0) == 2.0  # override smaller
    rec.range_km = 50.0
    assert state.effective_range(rec, 5.0) == 5.0  # capped by global

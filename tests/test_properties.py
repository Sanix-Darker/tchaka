"""Pure property-based tests for geospatial + neighborhood logic.

Property coverage:
- P-GEO-1 non-negativity
- P-GEO-2 identity (zero distance for identical points)
- P-GEO-3 symmetry
- P-GEO-4 bounded by pi * R
- P-GEO-5 triangle inequality
- P-NBR-1 every neighbor within threshold
- P-NBR-2 excludes self
- P-NBR-3 pair-membership symmetry (the property the old union-find violated)
- P-NBR-4 completeness (no false negatives)
- P-NBR-5 order independence / determinism
- P-NBR-6 monotonic in threshold
"""

from __future__ import annotations

from math import pi

from hypothesis import given, settings
from hypothesis import strategies as st

from tchaka.geo import EARTH_RADIUS_KM, haversine_distance
from tchaka.state import AppState, Coord, UserRecord

lats = st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False)
lons = st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False)
EPS = 1e-6
MAX_GREAT_CIRCLE = pi * EARTH_RADIUS_KM


# --------------------------------------------------------------------------- #
# Geo properties
# --------------------------------------------------------------------------- #
@given(lats, lons, lats, lons)
def test_haversine_nonneg_symmetric_bounded(a_lat, a_lon, b_lat, b_lon):
    d1 = haversine_distance(a_lat, a_lon, b_lat, b_lon)
    d2 = haversine_distance(b_lat, b_lon, a_lat, a_lon)
    assert d1 >= 0  # P-GEO-1
    assert abs(d1 - d2) <= EPS  # P-GEO-3
    assert d1 <= MAX_GREAT_CIRCLE + EPS  # P-GEO-4


@given(lats, lons)
def test_haversine_identity(lat, lon):
    assert haversine_distance(lat, lon, lat, lon) <= EPS  # P-GEO-2


@given(lats, lons, lats, lons, lats, lons)
def test_haversine_triangle_inequality(a_lat, a_lon, b_lat, b_lon, c_lat, c_lon):
    d_ac = haversine_distance(a_lat, a_lon, c_lat, c_lon)
    d_ab = haversine_distance(a_lat, a_lon, b_lat, b_lon)
    d_bc = haversine_distance(b_lat, b_lon, c_lat, c_lon)
    # P-GEO-5: allow a small relative tolerance for float error.
    assert d_ac <= d_ab + d_bc + 1e-6 * (1 + d_ab + d_bc)


# --------------------------------------------------------------------------- #
# Neighborhood properties
# --------------------------------------------------------------------------- #
def _build_state(coords: list[tuple[float, float]]) -> AppState:
    state = AppState()
    for i, (lat, lon) in enumerate(coords):
        state.register(
            UserRecord(
                user_id=f"u{i}",
                chat_id=i,
                coord=Coord(lat, lon),
                last_active_ts=0.0,
            )
        )
    return state


coord_lists = st.lists(st.tuples(lats, lons), min_size=1, max_size=25)
thresholds = st.floats(min_value=0.0, max_value=20100, allow_nan=False)


@settings(max_examples=150)
@given(coord_lists, thresholds)
def test_neighbors_within_threshold_and_excludes_self(coords, threshold):
    state = _build_state(coords)
    for uid, rec in state.users.items():
        for n in state.neighbors(uid, threshold):
            assert n.user_id != uid  # P-NBR-2
            d = haversine_distance(
                rec.coord.lat, rec.coord.lon, n.coord.lat, n.coord.lon
            )
            assert d <= threshold + 1e-9  # P-NBR-1


@settings(max_examples=150)
@given(coord_lists, thresholds)
def test_neighbor_membership_symmetric(coords, threshold):
    state = _build_state(coords)
    for uid in list(state.users):
        for n in state.neighbors(uid, threshold):
            back = {r.user_id for r in state.neighbors(n.user_id, threshold)}
            assert uid in back  # P-NBR-3


@settings(max_examples=150)
@given(coord_lists, thresholds)
def test_neighbors_completeness(coords, threshold):
    state = _build_state(coords)
    for uid, rec in state.users.items():
        expected = {
            other_uid
            for other_uid, other in state.users.items()
            if other_uid != uid
            and haversine_distance(
                rec.coord.lat, rec.coord.lon, other.coord.lat, other.coord.lon
            )
            <= threshold
        }
        got = {n.user_id for n in state.neighbors(uid, threshold)}
        assert got == expected  # P-NBR-4


@settings(max_examples=100)
@given(coord_lists, thresholds)
def test_neighbors_order_independent(coords, threshold):
    state_a = _build_state(coords)
    state_b = _build_state(list(reversed(coords)))
    # Map by coordinate so we can compare regardless of insertion order.
    for uid_a, rec_a in state_a.users.items():
        nbrs_a = {
            (round(n.coord.lat, 9), round(n.coord.lon, 9))
            for n in state_a.neighbors(uid_a, threshold)
        }
        # find the matching user in state_b by identical coordinate
        match = next(
            uid_b
            for uid_b, rec_b in state_b.users.items()
            if rec_b.coord == rec_a.coord
        )
        nbrs_b = {
            (round(n.coord.lat, 9), round(n.coord.lon, 9))
            for n in state_b.neighbors(match, threshold)
        }
        assert nbrs_a == nbrs_b  # P-NBR-5


@settings(max_examples=100)
@given(
    coord_lists,
    st.floats(min_value=0.0, max_value=10000, allow_nan=False),
    st.floats(min_value=0.0, max_value=10000, allow_nan=False),
)
def test_neighbors_monotonic_in_threshold(coords, t1, t2):
    lo, hi = min(t1, t2), max(t1, t2)
    state = _build_state(coords)
    for uid in list(state.users):
        small = {n.user_id for n in state.neighbors(uid, lo)}
        big = {n.user_id for n in state.neighbors(uid, hi)}
        assert small <= big  # P-NBR-6

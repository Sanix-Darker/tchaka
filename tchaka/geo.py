"""Pure geospatial helpers for tchaka.

These functions are deliberately free of any Telegram or state dependency so
they can be exhaustively property-tested in isolation and reused by both
:mod:`tchaka.state` (for the ego-centric neighborhood query) and
:mod:`tchaka.core`.
"""

from __future__ import annotations

from collections import defaultdict
from math import atan2, cos, radians, sin, sqrt

__all__ = [
    "EARTH_RADIUS_KM",
    "haversine_distance",
    "group_coordinates",
]

EARTH_RADIUS_KM = 6_371.0088
_DISTANCE_DEGREE_KM = 111.32  # mean km length of 1 degree of latitude


def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    /,
    *,
    radius: float = EARTH_RADIUS_KM,
) -> float:
    """Great-circle distance **in kilometres** between two WGS-84 points.

    Pure and deterministic. Properties (see design P-GEO-*): non-negative,
    zero iff identical points, symmetric, bounded by ``pi * radius``, obeys the
    triangle inequality.

    Reference:
        https://gis.stackexchange.com/questions/178201/calculate-the-distance-between-two-coordinates-wgs84-in-etrs89
    """
    phi1, lam1, phi2, lam2 = map(radians, (lat1, lon1, lat2, lon2))
    dphi, dlam = phi2 - phi1, lam2 - lam1
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return radius * 2 * atan2(sqrt(a), sqrt(1 - a))


def _hash_cell(lat: float, lon: float, cell_km: float) -> tuple[int, int]:
    """Bucket a lat/lon into a square cell of about *cell_km* km."""
    step = cell_km / _DISTANCE_DEGREE_KM
    return int(lat / step), int(lon / step)


def group_coordinates(
    coordinates: list[tuple[float, float]],
    *,
    distance_threshold: int = 100,
    user_coords: tuple[float, float] | None = None,
) -> tuple[dict[str, list[tuple[float, float]]], int]:
    """Cluster *coordinates* by geographic proximity (union-find over a spatial
    hash).

    NOTE: this is a transitive clustering retained only as an internal
    analytic helper. The user-facing "people around you" semantics use the
    ego-centric, non-transitive neighborhood in :meth:`AppState.neighbors`
    instead (see the design's Grouping Model Decision).

    ``returns (groups, n_users_in_current_user_group)``
    """

    if not coordinates:
        return {}, 0

    cell_km = max(distance_threshold, 50)  # at least 50 km cells for hashing
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, (lat, lon) in enumerate(coordinates):
        cells[_hash_cell(lat, lon, cell_km)].append(idx)

    parent = list(range(len(coordinates)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        pi, pj = find(i), find(j)
        if pi != pj:
            parent[pj] = pi

    neighbours = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]

    for (cx, cy), idxs in cells.items():
        candidate_idxs: list[int] = []
        for dx, dy in neighbours:
            candidate_idxs.extend(cells.get((cx + dx, cy + dy), []))

        for i in idxs:
            lat_i, lon_i = coordinates[i]
            for j in candidate_idxs:
                if j <= i:
                    continue  # skip duplicate checks
                lat_j, lon_j = coordinates[j]
                if (
                    abs(lat_i - lat_j) * _DISTANCE_DEGREE_KM > distance_threshold
                    or abs(lon_i - lon_j) * _DISTANCE_DEGREE_KM > distance_threshold
                ):
                    continue  # cheap reject
                if haversine_distance(lat_i, lon_i, lat_j, lon_j) <= distance_threshold:
                    union(i, j)

    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for idx, coord in enumerate(coordinates):
        gid = f"G-{find(idx)}"
        groups[gid].append(coord)

    users_in_same_group = 0
    if user_coords is not None:
        for members in groups.values():
            if user_coords in members:
                users_in_same_group = len(members)
                break

    return dict(groups), users_in_same_group

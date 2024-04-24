from functools import lru_cache
from math import radians, sin, cos, sqrt, atan2

@lru_cache
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points
    on the Earth's surface using the Haversine formula.

    """

    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    a = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = 6371 * c  # Radius of Earth in kilometers (BY THE WAY)
    return distance

# FIXME : PLEASE: this is not optimal at all LMAO
# (will fix that when i have more time)
async def group_coordinates(
    coordinates: list[tuple[float, float]],
    distance_threshold: int = 100,
) -> dict[str, tuple]:
    """
    Group coordinates based on their proximity within a certain distance threshold.
    Returns a dictionary with group IDs as keys and lists of coordinates as values.

    """

    groups = {}
    for coord in coordinates:
        group_found = False
        for group_id, group_coords in groups.items():
            if any(
                haversine_distance(
                    coord[0], coord[1], existing_coord[0], existing_coord[1]
                )
                <= distance_threshold
                for existing_coord in group_coords
            ):
                groups[group_id].append(coord)
                group_found = True
                break
        if not group_found:
            groups[f"___G-{len(groups)+1}"] = [coord]

    return groups

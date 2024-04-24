import pytest

from tchaka.core import group_coordinates, haversine_distance


@pytest.mark.anyio
@pytest.mark.parametrize(
    "lat1, lon1, lat2, lon2, expected_distance",
    [
        (52.5200, 13.4050, 52.5201, 13.4051, 0.013),
        (52.5200, 13.4050, 52.5205, 13.4055, 0.065),
        (52.5200, 13.4050, 52.5210, 13.4060, 0.13),
    ],
)
async def test_haversine_distance(lat1, lon1, lat2, lon2, expected_distance):
    calculated_distance = haversine_distance(lat1, lon1, lat2, lon2)
    assert round(calculated_distance, 3) == expected_distance


@pytest.mark.anyio
async def test_group_coordinates():
    coordinates = [
        (52.5200, 13.4050),
        (2.5201, 4.4051),
        (2.8205, 4.0055),
        (52.5200, 13.4060),
    ]
    grouped_coordinates = await group_coordinates(
        coordinates,
        distance_threshold=100,
    )

    assert len(grouped_coordinates) == 2  # Expecting two groups

    # Ensure each group contains at least one coordinate
    assert all(len(coords) >= 1 for coords in grouped_coordinates.values())

    # Ensure all coordinates within each group are within the distance threshold
    for group_coords in grouped_coordinates.values():
        for i in range(len(group_coords)):
            for j in range(i + 1, len(group_coords)):
                assert (
                    haversine_distance(
                        group_coords[i][0],
                        group_coords[i][1],
                        group_coords[j][0],
                        group_coords[j][1],
                    )
                    <= 100
                )

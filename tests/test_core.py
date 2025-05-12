import pytest
from datetime import datetime
from unittest.mock import AsyncMock, ANY
from pytest_mock import MockType, MockerFixture
from telegram import Message

from tchaka.core import (
    dispatch_msg_in_group,
    group_coordinates,
    haversine_distance,
    notify_all_user_on_the_same_group_for_join,
    populate_new_user_to_appropriate_group,
)


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
    grouped_coordinates, count_u = await group_coordinates(
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


@pytest.mark.asyncio
async def test_dispatch_msg_in_group(mocker: MockerFixture) -> None:
    ctx_mock = mocker.Mock()
    ctx_mock.bot.send_message = AsyncMock()

    user_list = {
        "user1": [123, (5.2, 64.0)],
        "user2": [552, (5.3, 60.0)],
        "user3": [456, (7.0, 80.0)],
    }
    group_list = {
        "group1": [(5.2, 64.0), (5.3, 60.0)],
        "group2": [(7.0, 80.0)],
    }

    await dispatch_msg_in_group(
        ctx_mock,
        "user1",
        Message(
            message_id=1,
            chat=ANY,
            text="Test message",
            date=datetime.now(),
        ),
        user_list,
        group_list,
    )

    assert ctx_mock.bot.send_message.call_count == 1


@pytest.mark.asyncio
async def test_notify_all_user_on_the_same_group_for_join(
    mocker: MockerFixture,
) -> None:
    ctx_mock = mocker.Mock()
    ctx_mock.bot.send_message = AsyncMock()

    user_list = {
        "user1": [123, (50.0, 60.0)],
        "user2": [456, (70.0, 80.0)],
    }

    await notify_all_user_on_the_same_group_for_join(ctx_mock, 123, "user1", user_list)

    assert ctx_mock.bot.send_message.call_count == 1


@pytest.mark.anyio
async def test_populate_new_user_to_appropriate_group(
    mocker: MockType,
) -> None:
    mocker.patch(
        "tchaka.core.group_coordinates", return_value=({"group1": [(50.0, 60.0)]}, 1)
    )

    new_user_name = "user1"
    current_chat_id = 123
    latitude = 50.0
    longitude = 60.0

    (
        updated_user_list,
        updated_group_list,
        count_u,
    ) = await populate_new_user_to_appropriate_group(
        new_user_name, current_chat_id, latitude, longitude, {}, {}
    )

    assert updated_user_list == {"user1": [123, (50.0, 60.0)]}
    assert updated_group_list == {"group1": [(50.0, 60.0)]}

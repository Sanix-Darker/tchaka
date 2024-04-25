from functools import lru_cache
from math import radians, sin, cos, sqrt, atan2
from typing import Any

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from tchaka.utils import safe_truncate


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
) -> dict[str, list]:
    """
    Group coordinates based on their proximity within a certain distance threshold.
    Returns a dictionary with group IDs as keys and lists of coordinates as values.

    """

    groups: dict[str, list] = {}
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


def get_username_from_chat_id(
    chat_id: int,
    user_list: dict[str, Any],
) -> str:
    """
    For a given chat-id, we introspect to get the relative chat-id

    """

    return next(
        (
            username
            for username, chat_id_and_locations in user_list.items()
            if chat_id_and_locations[0] == chat_id
        ),
    )


async def dispatch_msg_in_group(
    ctx: ContextTypes.DEFAULT_TYPE,
    user_new_name: str,
    message: str,
    user_list: dict[str, Any],
    group_list: dict[str, Any],
) -> None:
    """
    To send a message to a group user in the same 'area'

    """

    if not (current_user_infos := user_list.get(user_new_name)):
        # User not found in the locations dictionary
        return

    # FIXME: this need to be fast... i had to use combined
    # those ugly loops... it's not optimal yet
    # will fix later (or MAYBE not lol).

    for _, grp_list_locations in group_list.items():
        if current_user_infos[1] in grp_list_locations:
            # Send message to all chat IDs in the group
            for usr, chat_id in {
                username: user_infos[0]
                for username, user_infos in user_list.items()
                if username != user_new_name and user_infos[1] in grp_list_locations
            }.items():
                await ctx.bot.send_message(
                    chat_id=chat_id,
                    text=f"___***`{usr}`***___ \n\n{await safe_truncate(message)}",
                    parse_mode=ParseMode.MARKDOWN,
                )
            return


async def notify_all_user_on_the_same_group_for_join(
    ctx: ContextTypes.DEFAULT_TYPE,
    current_chat_id: int,
    user_new_name: str,
    user_list: dict[str, Any],
) -> list:
    """
    Ping all users in the same group as the current that he/she/... joined

    """

    return [
        await ctx.bot.send_message(
            chat_id=chat_id_and_location[0],
            text=f"__{user_new_name} joined the area__",
            parse_mode=ParseMode.MARKDOWN,
        )
        for _, chat_id_and_location in user_list.items()
        if chat_id_and_location[0] != current_chat_id
    ]


async def populate_new_user_to_appropriate_group(
    user_new_name: str,
    current_chat_id: int,
    latitude: float,
    longitude: float,
    user_list: dict[str, Any],
    group_list: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    This method set the user infos and put him in a group

    """

    user_list[user_new_name] = [current_chat_id, (latitude, longitude)]
    group_list = await group_coordinates(
        coordinates=[user_info[1] for user_info in user_list.values()],
        distance_threshold=100,
    )

    return user_list, group_list

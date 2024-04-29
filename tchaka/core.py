from asyncio import sleep
from functools import lru_cache, partial
from math import radians, sin, cos, sqrt, atan2
from typing import Any

from telegram import Message
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import Forbidden, BadRequest
from tchaka.utils import html_format_text, safe_truncate
from tchaka.utils import logging

_LOGGER = logging.getLogger(__name__)
MAX_BAD_REQUEST_ERROR = 10


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


async def dispatch_msg_in_group(
    ctx: ContextTypes.DEFAULT_TYPE,
    user_new_name: str,
    message: Message,
    user_list: dict[str, Any],
    group_list: dict[str, Any],
) -> None:
    """
    To send a message to a group user in the same 'area'

    """

    from tchaka.commands import append_chat_ids_messages  # cuz circular import

    if not (current_user_infos := user_list.get(user_new_name)):
        # User not found in the locations dictionary
        return

    current_user_location = current_user_infos[1]

    # FIXME: this need to be fast... i had to use combined
    # those ugly loops... it's not optimal yet
    # will fix later (or MAYBE not lol).

    for _, grp_list_locations in group_list.items():
        if current_user_location in grp_list_locations:
            try:
                # Send message to all chat IDs in the group
                for usr, chat_id in {
                    username: user_infos[0]
                    for username, user_infos in user_list.items()
                    if username != user_new_name and user_infos[1] in grp_list_locations
                }.items():
                    msg = safe_truncate(message.text, 200)
                    bot_send_message = partial(
                        ctx.bot.send_message,
                        chat_id=chat_id,
                        text=f"__**{user_new_name}**__ \n\n{msg}",
                        parse_mode=ParseMode.MARKDOWN,
                    )

                    try:
                        # If it's a reply, quote it
                        if (
                            (replying_to := message.reply_to_message) is not None
                            and replying_to.text is not None
                            and (quote_block := replying_to.text.split("\n"))
                        ):
                            # The quote is the last 10 chars
                            quote_usr = quote_block[0]
                            quote_msg = safe_truncate(quote_block[-1])
                            await bot_send_message(
                                text=f"__**{user_new_name}**__ \n```{quote_usr}{quote_msg}```\n {msg}",
                            )

                            assert message.reply_to_message is not None
                            await append_chat_ids_messages(
                                chat_id, message.reply_to_message.message_id
                            )
                        else:
                            await bot_send_message()
                            await append_chat_ids_messages(chat_id, message.message_id)
                    except (ValueError, AssertionError) as excp:
                        _LOGGER.warning(
                            "ValueError | AssertionError maybe on reply", exc_info=excp
                        )
                        await bot_send_message()
                        await append_chat_ids_messages(chat_id, message.message_id)
                    except Exception as excp:
                        # pass the iteration on next step on error
                        _LOGGER.warning(
                            f"Unable to send message to {usr=}", exc_info=excp
                        )
            except Exception as excp:
                _LOGGER.warning(
                    "Error looping on chatIds to send message", exc_info=excp
                )

            return


async def notify_all_user_on_the_same_group_for_join(
    ctx: ContextTypes.DEFAULT_TYPE,
    current_chat_id: int,
    user_new_name: str,
    user_list: dict[str, Any],
) -> None:
    """
    Ping all users in the same group as the current that he/she/... joined

    """

    for _, chat_id_and_location in user_list.items():
        if chat_id_and_location[0] != current_chat_id:
            try:
                await ctx.bot.send_message(
                    chat_id=chat_id_and_location[0],
                    text=html_format_text(f"{user_new_name} joined the area..."),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except (Forbidden, BadRequest) as excp:
                _LOGGER.warning(f"WOUPS {chat_id_and_location[0]}", exc_info=excp)


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


async def clean_all_msg(
    message: Message,
    ctx: ContextTypes.DEFAULT_TYPE,
    list_of_msg_ids: list[int],
) -> None:
    """
    ATTENTION: this method is CURSED and it's trying to self doing
    something not implemented yet byt PTB API, will fix it later

    In reverse, from the latest message_id
    delete all messages sent on a chat
    until error and stop

    """

    await sleep(1)

    bad_request_count = 0
    if not list_of_msg_ids:
        messages_to_delete = message.message_id - 3
        while True:
            try:
                await ctx.bot.delete_message(
                    chat_id=message.chat_id,
                    message_id=messages_to_delete,
                )
                messages_to_delete += 1
            except BadRequest:
                bad_request_count += 1
                if bad_request_count == MAX_BAD_REQUEST_ERROR:
                    break
            except Exception as excp:
                _LOGGER.warning("Deletion failed", exc_info=excp)
                break
    else:
        for msg_id in list_of_msg_ids:
            try:
                # NOTE: Emulate do_while here to delete all messages between
                # something sent from the user and all by the bot or other
                # users.
                # - 3 because we need to delete the '/stop' and the 'goodby message'
                msg_id_to_delete = msg_id - 3
                while True:
                    await ctx.bot.delete_message(
                        chat_id=message.chat_id,
                        message_id=msg_id_to_delete,
                    )
                    msg_id_to_delete += 1
            except BadRequest:
                bad_request_count += 1
                if bad_request_count == MAX_BAD_REQUEST_ERROR:
                    break
            except Exception as excp:
                _LOGGER.warning("Deletion failed", exc_info=excp)
                break

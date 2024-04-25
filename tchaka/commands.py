from functools import lru_cache
import json
from typing import Any
from telegram import Update
import html
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from tchaka.core import group_coordinates
from tchaka.utils import (
    build_user_hash,
    build_welcome_location_message_for_current_user,
    get_user_and_message,
    safe_truncate,
    logging,
)
from tchaka.config import DEVELOPER_CHAT_ID, LANG_MESSAGES
import traceback

_LOGGER = logging.getLogger(__name__)
_USERS: dict[str, Any] = {}
_GROUPS: dict[str, Any] = {}


async def start_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    StartCallBack to instantiate the bot
    Check for bot before fetching the chat-id and respond.

    """
    user, message = await get_user_and_message(update)

    welcome_message = LANG_MESSAGES[user.language_code or "en"]["WELCOME_MESSAGE"]
    await message.reply_text(text=f"{welcome_message} {message.chat_id}")
    _LOGGER.info(f"/start :: send_message :: {user.full_name=}")


async def help_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    HelpCallBack to respond with a small help message.

    """
    user, message = await get_user_and_message(update)

    help_message = LANG_MESSAGES[user.language_code or "en"]["HELP_MESSAGE"]
    await message.reply_text(text=f"{help_message}")
    # _LOGGER.info(f"/help :: send_message :: {message.chat_id=}")


@lru_cache
def get_username_from_chat_id(chat_id: int) -> str:
    global _USERS

    return next(
        (
            username
            for username, chat_id_and_locations in _USERS.items()
            if chat_id_and_locations[0] == chat_id
        ),
    )


async def echo_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    EchoCallBack to respond with a small help message.

    """
    _, message = await get_user_and_message(update)

    message_txt = await safe_truncate(message.text)

    if user_new_name := get_username_from_chat_id(message.chat_id):
        await dispatch_msg_in_group(
            ctx=ctx, user_new_name=user_new_name, message=message_txt
        )
        _LOGGER.info(f"/echo :: send_message :: {user_new_name=} :: {message_txt}")
    else:
        _LOGGER.warning(f"/echo :: send_message :: {user_new_name=} :: {message_txt}")


async def dispatch_msg_in_group(
    ctx: ContextTypes.DEFAULT_TYPE, user_new_name: str, message: str
) -> None:
    global _USERS

    if not (current_user_infos := _USERS.get(user_new_name)):
        # User not found in the locations dictionary
        return

    user_location = current_user_infos[1]

    # FIXME: this need to be fast... i had to use combined
    # list comprehension but yeah... it's not optimal yet
    # will fix later (or MAYBE not lol).

    for _, grp_list_locations in _GROUPS.items():
        if user_location in grp_list_locations:
            # Send message to all chat IDs in the group
            for usr, chat_id in {
                username: user_infos[0]
                for username, user_infos in _USERS.items()
                if username != user_new_name and user_infos[1] in grp_list_locations
            }.items():
                await ctx.bot.send_message(
                    chat_id=chat_id,
                    text=f"___***`{usr}`***___ \n\n{await safe_truncate(message)}",
                    parse_mode=ParseMode.MARKDOWN,
                )
            return


async def notify_all_user_on_the_same_group_for_join(
    ctx: ContextTypes.DEFAULT_TYPE, current_chat_id: int, user_new_name: str
) -> None:
    global _USERS

    (
        await ctx.bot.send_message(
            chat_id=chat_id_and_location[0],
            text=f"__{user_new_name} joined the area__",
            parse_mode=ParseMode.MARKDOWN,
        )
        for _, chat_id_and_location in _USERS.items()
        if chat_id_and_location[0] != current_chat_id
    )


async def populate_new_user_to_appropriate_group(
    user_new_name: str, current_chat_id: int, latitude: float, longitude: float
) -> None:
    global _GROUPS, _USERS

    _USERS[user_new_name] = [current_chat_id, (latitude, longitude)]
    _GROUPS = await group_coordinates(
        coordinates=[user_info[1] for user_info in _USERS.values()],
        distance_threshold=100,
    )


async def location_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    LocationCallBack to handle location messages.

    """
    global _USERS

    user, message = await get_user_and_message(update)
    user_new_name = await build_user_hash(user.full_name)

    if not (location := message.location):
        raise Exception("Location unable to be extracted ")

    await populate_new_user_to_appropriate_group(
        user_new_name=user_new_name,
        current_chat_id=message.chat_id,
        latitude=location.latitude,
        longitude=location.longitude,
    )

    await notify_all_user_on_the_same_group_for_join(
        ctx=ctx, current_chat_id=message.chat_id, user_new_name=user_new_name
    )

    await message.reply_markdown(
        text=build_welcome_location_message_for_current_user(
            user_new_name,
            _USERS,
            user.language_code or "en",
        )
    )

    _LOGGER.info(f"/location :: location_callback :: {user_new_name=}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    _LOGGER.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    assert DEVELOPER_CHAT_ID is not None
    await context.bot.send_message(
        chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML
    )

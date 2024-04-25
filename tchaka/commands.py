import json
from typing import Any
from telegram import Update
import html
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from tchaka.core import group_coordinates
from tchaka.utils import build_user_hash, get_user_and_message, safe_truncate, logging
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
    _LOGGER.info(f"/help :: send_message :: {user.full_name=}")


async def echo_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    EchoCallBack to respond with a small help message.

    """
    user, message = await get_user_and_message(update)

    message_txt = await safe_truncate(message.text)
    # TODO: do something here when needed
    _LOGGER.info(f"/echo :: send_message :: {user.full_name=} :: {message_txt}")


async def dispatch_msg_in_group(
    ctx: ContextTypes.DEFAULT_TYPE, user_new_name: str, message: str
) -> None:
    global _USERS_CHAT_IDS

    if not (user_location := _USERS.get(user_new_name)):
        # User not found in the locations dictionary
        return

    # FIXME: this need to be fast... i had to use combined
    # list comprehension but yeah... it's not optimal yet
    # will fix later (MAYBE).
    (
        # Extract chat IDs from the group
        # and send messages
        (
            await ctx.bot.send_message(
                chat_id=user_infos[0],  # chat_id
                text=await safe_truncate(message),
                parse_mode=ParseMode.MARKDOWN,
            )
            for username, user_infos in _USERS.items()
            if username != user_new_name and user_infos[1] in grp_list_locations
        )
        for _, grp_list_locations in _GROUPS.items()
        if user_location in grp_list_locations
    )


async def notify_same_group_on_join(
    ctx: ContextTypes.DEFAULT_TYPE, current_chat_id: int, user_new_name: str
) -> None:
    global _USERS_CHAT_IDS

    (
        await ctx.bot.send_message(
            chat_id=u_chat_id,
            text=f"__{user_new_name} joined the area__",
            parse_mode=ParseMode.MARKDOWN,
        )
        for u_chat_id in _USERS.keys()
        if u_chat_id != current_chat_id
    )


async def populate_new_user_group(
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

    await populate_new_user_group(
        user_new_name=user_new_name,
        current_chat_id=message.chat_id,
        latitude=location.latitude,
        longitude=location.longitude,
    )

    await notify_same_group_on_join(
        ctx=ctx, current_chat_id=message.chat_id, user_new_name=user_new_name
    )

    suggest_to_connect = (
        (
            f"There is ({len(_USERS)-1}) people in the same 'area' than "
            "you and they just get notified.\n"
            "Feel free to say 'hi'.\n"
        )
        if len(_USERS) > 1
        else ("0 users here for now.\n")
    )
    await message.reply_markdown(
        text=(
            f"Location received !!!\n"
            f"Now, your're ***__{user_new_name}__***.\n"
            f"{suggest_to_connect}\n"
            "Note: Everything here is encrypted and the chat will be cleaned when you change place.\n"
        )
    )
    _LOGGER.info(f"/location :: send_message :: {user_new_name=}")


# TODO:
# dir (list files)
# search (search for files)


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

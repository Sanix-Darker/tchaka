import json
from typing import Any
from telegram import Update
import html
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from tchaka.core import (
    dispatch_msg_in_group,
    get_username_from_chat_id,
    notify_all_user_on_the_same_group_for_join,
    populate_new_user_to_appropriate_group,
)
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


async def echo_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    EchoCallBack to respond with a small help message.

    """
    global _USERS, _GROUPS

    _, message = await get_user_and_message(update)
    message_txt = await safe_truncate(message.text)

    if user_new_name := get_username_from_chat_id(message.chat_id, _USERS):
        await dispatch_msg_in_group(
            ctx=ctx,
            user_new_name=user_new_name,
            message=message_txt,
            user_list=_USERS,
            group_list=_GROUPS,
        )
        _LOGGER.info(f"/echo :: send_message :: {user_new_name=} :: {message_txt}")
    else:
        _LOGGER.warning(f"/echo :: send_message :: {user_new_name=} :: {message_txt}")


async def location_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    LocationCallBack to handle location messages.

    """
    global _USERS, _GROUPS

    user, message = await get_user_and_message(update)
    user_new_name = await build_user_hash(user.full_name)

    if not (location := message.location):
        raise Exception("Location unable to be extracted ")

    if user_and_group := await populate_new_user_to_appropriate_group(
        user_new_name=user_new_name,
        current_chat_id=message.chat_id,
        latitude=location.latitude,
        longitude=location.longitude,
        user_list=_USERS,
        group_list=_GROUPS,
    ):
        _USERS, _GROUPS = user_and_group

        await notify_all_user_on_the_same_group_for_join(
            ctx=ctx,
            current_chat_id=message.chat_id,
            user_new_name=user_new_name,
            user_list=_USERS,
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

import json
from typing import Any
from telegram import Update
import html
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from tchaka.core import (
    clean_all_msg,
    dispatch_msg_in_group,
    notify_all_user_on_the_same_group_for_join,
    populate_new_user_to_appropriate_group,
)
from tchaka.utils import (
    build_user_hash,
    build_welcome_location_message_for_current_user,
    get_user_and_message,
    html_format_text,
    logging,
)
from tchaka.config import DEVELOPER_CHAT_ID, LANG_MESSAGES
import traceback

_LOGGER = logging.getLogger(__name__)
# usersnames mapped to locations
_USERS: dict[str, Any] = {}
# chat-ids mapped to random usernames
_CHAT_IDS: dict[int, str] = {}
_CHAT_IDS_MSGS: dict[int, list[int]] = {}
_GROUPS: dict[str, Any] = {}


async def append_chat_ids_messages(
    chat_id: int, message_id: int
) -> dict[int, list[int]]:
    global _CHAT_IDS_MSGS

    if chat_id in _CHAT_IDS_MSGS:
        latest_inserted = _CHAT_IDS_MSGS[chat_id][-1]
        # supposing the new message_id will always be > latest_inserted
        while latest_inserted < message_id:
            latest_inserted += 1
            _CHAT_IDS_MSGS[chat_id].append(latest_inserted)
    else:
        _CHAT_IDS_MSGS[chat_id] = [message_id]

    return _CHAT_IDS_MSGS


async def start_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    StartCallBack to instantiate the bot
    Check for bot before fetching the chat-id and respond.

    """
    user, message = await get_user_and_message(update)

    if not (given_user_name := _CHAT_IDS.get(message.chat_id)):
        given_user_name = "New User"

    await append_chat_ids_messages(message.chat_id, message.message_id)

    welcome_message = LANG_MESSAGES[user.language_code or "en"]["WELCOME_MESSAGE"]
    await message.reply_text(text=html_format_text(welcome_message))
    _LOGGER.info(f"/start :: {given_user_name=}")


async def check_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    CheckCallBack to check how many people are in the area

    """

    _, message = await get_user_and_message(update)

    await append_chat_ids_messages(message.chat_id, message.message_id)

    if not (given_user_name := _CHAT_IDS.get(message.chat_id)):
        given_user_name = "New User"
        await message.reply_text(
            text="Send your localisation to be put in a group first please"
        )
        return

    await message.reply_text(text="There is ---")
    _LOGGER.info(f"/start :: {given_user_name=}")


async def stop_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    StopCallBack to stop following

    """

    _, message = await get_user_and_message(update)

    if not (given_user_name := _CHAT_IDS.get(message.chat_id)):
        given_user_name = "New User"
        msg = "Not In the current chat flow, bot stoped."
    else:
        # we don't care about groups, since it's rewrote on each call
        # yes not optimial at all
        _USERS.pop(given_user_name, None)
        _CHAT_IDS.pop(message.chat_id, None)
        msg = f"Thanks using tchaka {given_user_name}, bot stoped.\nAll messages are going to be deleted."

    await append_chat_ids_messages(message.chat_id, message.message_id)
    await message.reply_text(text=html_format_text(msg))

    await clean_all_msg(
        message=message, ctx=ctx, list_of_msg_ids=_CHAT_IDS_MSGS[message.chat_id]
    )

    _LOGGER.info(f"/stopped :: {given_user_name}")


async def help_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    HelpCallBack to respond with a small help message.

    """
    user, message = await get_user_and_message(update)

    if not (given_user_name := _CHAT_IDS.get(message.chat_id)):
        given_user_name = "New User"

    help_message = LANG_MESSAGES[user.language_code or "en"]["HELP_MESSAGE"]

    await append_chat_ids_messages(message.chat_id, message.message_id)
    await message.reply_text(text=html_format_text(f"{help_message}"))
    _LOGGER.info(f"/help :: {given_user_name}")


async def echo_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    EchoCallBack to respond with a small help message.

    """
    global _USERS, _GROUPS, _CHAT_IDS

    _, message = await get_user_and_message(update)

    # SHould do nothing if the user is not yet in the system
    if not (given_user_name := _CHAT_IDS.get(message.chat_id)):
        given_user_name = "New User"
        _LOGGER.info(f"/echo :: {given_user_name}")
        return

    if user_new_name := _CHAT_IDS.get(message.chat_id):
        await dispatch_msg_in_group(
            ctx=ctx,
            user_new_name=user_new_name,
            message=message,
            user_list=_USERS,
            group_list=_GROUPS,
        )
        _LOGGER.info(f"/echo :: {user_new_name=}")
    else:
        _LOGGER.warning(f"/echo :: {user_new_name=}")


async def location_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    LocationCallBack to handle location messages.

    """

    global _USERS, _GROUPS, _CHAT_IDS

    user, message = await get_user_and_message(update)

    # already tracked
    if message.chat_id in _CHAT_IDS:
        return

    if not (location := message.location):
        raise Exception("Location unable to be extracted ")

    user_new_name = await build_user_hash(user.full_name)

    await append_chat_ids_messages(message.chat_id, message.message_id)
    (
        _USERS,
        _GROUPS,
        count_user_same_group,
    ) = await populate_new_user_to_appropriate_group(
        user_new_name=user_new_name,
        current_chat_id=message.chat_id,
        latitude=location.latitude,
        longitude=location.longitude,
        user_list=_USERS,
        group_list=_GROUPS,
    )

    _CHAT_IDS[message.chat_id] = user_new_name

    await notify_all_user_on_the_same_group_for_join(
        ctx=ctx,
        current_chat_id=message.chat_id,
        user_new_name=user_new_name,
        user_list=_USERS,
    )

    await message.reply_markdown(
        text=html_format_text(
            build_welcome_location_message_for_current_user(
                user_new_name,
                count_user_same_group,
                user.language_code or "en",
            )
        )
    )

    _LOGGER.info(f"/location :: {user_new_name=}")


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

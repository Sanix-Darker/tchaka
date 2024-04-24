import json
from telegram import Update
import html
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from tchaka.core import group_coordinates
from tchaka.utils import build_user_hash, get_user_and_message, safe_truncate, logging
from tchaka.config import DEVELOPER_CHAT_ID, LANG_MESSAGES
import traceback

_LOGGER = logging.getLogger(__name__)
_USERS_LOCATIONS = {}
_USERS_CHAT_IDS = {}
_GROUPS = {}


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


async def location_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    LocationCallBack to handle location messages.

    """
    user, message = await get_user_and_message(update)
    user_new_name = await build_user_hash(user.full_name)

    if not (location := message.location):
        raise Exception("Location unable to be extracted ")

    _USERS_LOCATIONS[user_new_name] = (location.latitude, location.longitude)
    _USERS_CHAT_IDS[user_new_name] = message.chat_id

    _GROUPS = await group_coordinates(
        coordinates=list(_USERS_LOCATIONS.values()),
        distance_threshold=100,
    )

    print(">> _GROUPS: ", _GROUPS)
    print(">> _USERS_CHAT_IDS: ", _USERS_CHAT_IDS)
    print(">> _USERS_LOCATIONS: ", _USERS_LOCATIONS)

    await message.reply_markdown(
        text=(
            f"Location received !!!\n"
            f"Now, your're **{user_new_name}**."
            f"There are ({len(_USERS_CHAT_IDS)-1}) people in the same 'area' than you and they just get notified."
            "Feel free to say 'hi'."
            "Note: Everything here is encrypted and the chat will be cleaned when you change place."
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

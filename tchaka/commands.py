"""Telegram command/message callbacks (the I/O front-end of tchaka).

These callbacks are intentionally thin: they parse the ``Update``, do fast
in-memory work under ``STATE.lock``, snapshot any recipient list, release the
lock, then perform Telegram I/O. They contain no geospatial math (that lives in
:mod:`tchaka.core` / :mod:`tchaka.geo`).

Runtime singletons (``STATE``, ``SETTINGS``, ``CLOCK``) are initialized by
:mod:`tchaka.main` via :func:`configure`. Tests may call :func:`configure`
directly with a :class:`FakeClock` and a custom :class:`Settings`.
"""

from __future__ import annotations

import html
import json
import logging
import traceback

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from tchaka.config import LANG_MESSAGES, Settings, load_settings
from tchaka.core import (
    build_reply_excerpt,
    cleanup_messages,
    count_nearby,
    format_relay_body,
    notify_group_join,
    register_user,
    relay_message,
)
from tchaka.state import AppState, Coord
from tchaka.utils import (
    Clock,
    SystemClock,
    build_user_hash,
    build_welcome_location_message_for_current_user,
    get_user_and_message,
    html_format_text,
)

_LOGGER = logging.getLogger(__name__)

# Runtime singletons (configured at startup). Defaults let tests import the
# module without a real token; main.py calls configure() with loaded settings.
STATE: AppState = AppState()
CLOCK: Clock = SystemClock()
SETTINGS: Settings | None = None


def configure(
    *,
    state: AppState | None = None,
    settings: Settings | None = None,
    clock: Clock | None = None,
) -> None:
    """Wire the module-level singletons. Called by main.py and tests."""
    global STATE, SETTINGS, CLOCK
    if state is not None:
        STATE = state
    if settings is not None:
        SETTINGS = settings
    if clock is not None:
        CLOCK = clock


def _settings() -> Settings:
    """Return the active settings, loading them lazily if not configured."""
    global SETTINGS
    if SETTINGS is None:
        SETTINGS = load_settings()
    return SETTINGS


def _lang(language_code: str | None) -> dict[str, str]:
    return LANG_MESSAGES.get(language_code or "en", LANG_MESSAGES["en"])


async def start_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Greet the user and record the inbound + reply message ids."""
    user, message = await get_user_and_message(update)

    async with STATE.lock:
        rec = STATE.user_for_chat(message.chat_id)
        if rec is not None:
            STATE.touch(rec.user_id, CLOCK.now())
        STATE.track_message(message.chat_id, message.message_id)

    welcome_message = _lang(user.language_code)["WELCOME_MESSAGE"]
    sent = await message.reply_text(text=html_format_text(welcome_message))
    async with STATE.lock:
        STATE.track_message(message.chat_id, sent.message_id)
    _LOGGER.info("/start :: chat_id=%s", message.chat_id)


async def check_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Report how many other users are within the configured range."""
    user, message = await get_user_and_message(update)
    lang = _lang(user.language_code)
    threshold = _settings().distance_threshold_km

    async with STATE.lock:
        STATE.track_message(message.chat_id, message.message_id)
        rec = STATE.user_for_chat(message.chat_id)
        if rec is None:
            reply_text = lang["CHECK_NOT_REGISTERED"]
        else:
            STATE.touch(rec.user_id, CLOCK.now())
            count = count_nearby(STATE, rec.user_id, threshold)
            reply_text = (
                lang["CHECK_ALONE"]
                if count == 0
                else lang["CHECK_RESULT"].format(n=count)
            )

    sent = await message.reply_text(text=html_format_text(reply_text))
    async with STATE.lock:
        STATE.track_message(message.chat_id, sent.message_id)
    _LOGGER.info("/check :: chat_id=%s", message.chat_id)


async def stop_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the user from all state and purge their tracked messages."""
    _, message = await get_user_and_message(update)

    async with STATE.lock:
        STATE.track_message(message.chat_id, message.message_id)
        rec = STATE.remove_by_chat(message.chat_id)
        if rec is None:
            msg = "Not in the current chat flow, bot stopped."
            msg_ids: set[int] = STATE.pop_tracked(message.chat_id)
            given_user_name = f"chat_id {message.chat_id}"
        else:
            given_user_name = rec.user_id
            msg = (
                f"Thanks using tchaka {rec.user_id}, bot stopped.\n"
                "All messages are going to be deleted."
            )
            msg_ids = STATE.pop_tracked(message.chat_id)

    sent = await message.reply_text(text=html_format_text(msg))
    msg_ids.add(sent.message_id)

    await cleanup_messages(ctx.bot, message.chat_id, msg_ids)
    _LOGGER.info("/stop :: %s", given_user_name)


async def help_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with the localized help message."""
    user, message = await get_user_and_message(update)

    async with STATE.lock:
        rec = STATE.user_for_chat(message.chat_id)
        if rec is not None:
            STATE.touch(rec.user_id, CLOCK.now())
        STATE.track_message(message.chat_id, message.message_id)

    help_message = _lang(user.language_code)["HELP_MESSAGE"]
    sent = await message.reply_text(text=html_format_text(help_message))
    async with STATE.lock:
        STATE.track_message(message.chat_id, sent.message_id)
    _LOGGER.info("/help :: chat_id=%s", message.chat_id)


async def echo_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Relay a text message to everyone within the sender's range."""
    _, message = await get_user_and_message(update)
    threshold = _settings().distance_threshold_km
    max_chars = _settings().max_relay_chars

    async with STATE.lock:
        rec = STATE.user_for_chat(message.chat_id)
        if rec is None:
            # not registered -> do nothing
            _LOGGER.info("/echo :: unregistered chat_id=%s", message.chat_id)
            return
        STATE.touch(rec.user_id, CLOCK.now())
        recipients = [n.chat_id for n in STATE.neighbors(rec.user_id, threshold)]
        sender_id = rec.user_id

    if not recipients:
        return

    body = format_relay_body(
        sender_id, message.text, max_chars, build_reply_excerpt(message)
    )
    await relay_message(ctx.bot, STATE, body=body, recipients_snapshot=recipients)
    _LOGGER.info("/echo :: sender=%s recipients=%d", sender_id, len(recipients))


async def location_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Register a new user from their location and notify nearby users."""
    user, message = await get_user_and_message(update)
    threshold = _settings().distance_threshold_km

    if (location := message.location) is None:
        raise ValueError("Location unable to be extracted")

    user_new_name = await build_user_hash(user.full_name)

    async with STATE.lock:
        if STATE.user_for_chat(message.chat_id) is not None:
            return  # already tracked (idempotent)
        rec = register_user(
            STATE,
            user_id=user_new_name,
            chat_id=message.chat_id,
            coord=Coord(location.latitude, location.longitude),
            lang=user.language_code or "en",
            clock=CLOCK,
        )
        STATE.track_message(message.chat_id, message.message_id)
        recipients = [n.chat_id for n in STATE.neighbors(rec.user_id, threshold)]
        count = len(recipients)

    await notify_group_join(
        ctx.bot, STATE, new_user=rec, recipients_snapshot=recipients
    )

    sent = await message.reply_markdown(
        text=html_format_text(
            build_welcome_location_message_for_current_user(
                user_new_name,
                count,
                user.language_code or "en",
            )
        )
    )
    async with STATE.lock:
        STATE.track_message(message.chat_id, sent.message_id)
    _LOGGER.info("/location :: user=%s neighbors=%d", user_new_name, count)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and (if configured) forward a length-safe report to dev."""
    _LOGGER.error("Exception while handling an update:", exc_info=context.error)

    settings = _settings()
    if settings.developer_chat_id is None:
        _LOGGER.warning("DEVELOPER_CHAT_ID unset; error not forwarded to Telegram")
        return

    tb_list = traceback.format_exception(context.error)
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    raw = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    safe = raw[: settings.max_error_chars]

    try:
        await context.bot.send_message(
            chat_id=settings.developer_chat_id, text=safe, parse_mode=ParseMode.HTML
        )
    except Exception:
        _LOGGER.exception("Failed to deliver error report to developer")

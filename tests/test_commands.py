"""Tests for the Telegram callbacks (the I/O front-end).

Covers the rewired callbacks against a fresh AppState + FakeClock + test
Settings:
- start/help reply and track real ids
- /check returns counts (not the old "There is ---" stub) and handles the
  unregistered case
- /stop fully removes a user from all state
- /location registers and notifies only neighbors (Issue #6)
- /echo relays only to neighbors, never the sender
- error_handler is graceful when DEVELOPER_CHAT_ID is unset (Issue #10)
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from telegram import Message, Update, User
from telegram.ext import ContextTypes

import tchaka.commands as commands
from tchaka.config import Settings
from tchaka.state import AppState, Coord, UserRecord
from tchaka.utils import FakeClock


def _settings(
    *,
    developer_chat_id: int | None = None,
    distance_threshold_km: float = 5.0,
    max_error_chars: int = 3500,
) -> Settings:
    return Settings(
        tg_token="tok",
        developer_chat_id=developer_chat_id,
        distance_threshold_km=distance_threshold_km,
        idle_ttl_seconds=3600,
        sweep_interval_seconds=300,
        max_relay_chars=500,
        max_error_chars=max_error_chars,
    )


@pytest.fixture(autouse=True)
def fresh_state() -> AppState:
    state = AppState()
    commands.configure(state=state, settings=_settings(), clock=FakeClock(0.0))
    return state


@pytest.fixture
def update() -> MagicMock:
    uu = MagicMock(spec=Update)
    update_user = MagicMock(spec=User)
    update_user.language_code = "en"
    update_user.full_name = "John Doe"
    update_user.is_bot = False
    uupdate_message = MagicMock(spec=Message)
    uupdate_message.chat_id = 123
    uupdate_message.message_id = 1
    uu.effective_user = update_user
    uu.message = uupdate_message
    return uu


@pytest.fixture
def context() -> MagicMock:
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx.bot = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_start_callback(update: MagicMock, context: MagicMock) -> None:
    update.message.reply_text = AsyncMock(
        return_value=type("M", (), {"message_id": 2})()
    )
    await commands.start_callback(update, context)
    update.message.reply_text.assert_called_once_with(text=ANY)


@pytest.mark.asyncio
async def test_help_callback(update: MagicMock, context: MagicMock) -> None:
    update.message.reply_text = AsyncMock(
        return_value=type("M", (), {"message_id": 2})()
    )
    await commands.help_callback(update, context)
    update.message.reply_text.assert_called_once_with(text=ANY)


@pytest.mark.asyncio
async def test_check_unregistered(update: MagicMock, context: MagicMock) -> None:
    update.message.reply_text = AsyncMock(
        return_value=type("M", (), {"message_id": 2})()
    )
    await commands.check_callback(update, context)
    sent_text = update.message.reply_text.call_args.kwargs["text"]
    assert "location" in sent_text.lower()


@pytest.mark.asyncio
async def test_check_counts_neighbors(
    update: MagicMock, context: MagicMock, fresh_state: AppState
) -> None:
    # register the requesting user + one nearby + one far
    fresh_state.register(UserRecord("me", 123, Coord(52.5200, 13.4050), 0.0))
    fresh_state.register(UserRecord("near", 999, Coord(52.5201, 13.4051), 0.0))
    fresh_state.register(UserRecord("far", 888, Coord(48.8566, 2.3522), 0.0))
    update.message.reply_text = AsyncMock(
        return_value=type("M", (), {"message_id": 2})()
    )
    await commands.check_callback(update, context)
    sent_text = update.message.reply_text.call_args.kwargs["text"]
    assert "1" in sent_text  # exactly one neighbor within 5 km
    assert "---" not in sent_text  # the old stub is gone


@pytest.mark.asyncio
async def test_stop_fully_removes(
    update: MagicMock, context: MagicMock, fresh_state: AppState
) -> None:
    fresh_state.register(UserRecord("me", 123, Coord(0.0, 0.0), 0.0))
    fresh_state.track_message(123, 50)
    update.message.reply_text = AsyncMock(
        return_value=type("M", (), {"message_id": 2})()
    )
    await commands.stop_callback(update, context)
    assert "me" not in fresh_state.users
    assert 123 not in fresh_state.chat_to_user
    assert 123 not in fresh_state.tracked_msgs


@pytest.mark.asyncio
async def test_location_registers_and_notifies_only_neighbors(
    update: MagicMock, context: MagicMock, fresh_state: AppState
) -> None:
    # pre-existing near + far users
    fresh_state.register(UserRecord("near", 999, Coord(52.5201, 13.4051), 0.0))
    fresh_state.register(UserRecord("far", 888, Coord(48.8566, 2.3522), 0.0))
    update.message.location = type(
        "L", (), {"latitude": 52.5200, "longitude": 13.4050}
    )()
    update.message.reply_markdown = AsyncMock(
        return_value=type("M", (), {"message_id": 2})()
    )
    context.bot.send_message = AsyncMock(
        return_value=type("M", (), {"message_id": 7})()
    )
    await commands.location_callback(update, context)

    # the new user is registered
    assert 123 in fresh_state.chat_to_user
    # join notification went only to the near neighbor (chat 999), not far (888)
    notified = {c.kwargs["chat_id"] for c in context.bot.send_message.await_args_list}
    assert notified == {999}


@pytest.mark.asyncio
async def test_echo_relays_only_to_neighbors(
    update: MagicMock, context: MagicMock, fresh_state: AppState
) -> None:
    fresh_state.register(UserRecord("me", 123, Coord(52.5200, 13.4050), 0.0))
    fresh_state.register(UserRecord("near", 999, Coord(52.5201, 13.4051), 0.0))
    fresh_state.register(UserRecord("far", 888, Coord(48.8566, 2.3522), 0.0))
    update.message.text = "hello"
    update.message.reply_to_message = None
    context.bot.send_message = AsyncMock(
        return_value=type("M", (), {"message_id": 7})()
    )
    await commands.echo_callback(update, context)
    recipients = {c.kwargs["chat_id"] for c in context.bot.send_message.await_args_list}
    assert recipients == {999}  # near only; not self (123), not far (888)


@pytest.mark.asyncio
async def test_echo_unregistered_noop(update: MagicMock, context: MagicMock) -> None:
    update.message.text = "hello"
    context.bot.send_message = AsyncMock()
    await commands.echo_callback(update, context)
    context.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_error_handler_graceful_without_dev_id(context: MagicMock) -> None:
    # developer_chat_id is None in the default test settings.
    context.error = RuntimeError("boom")
    context.bot.send_message = AsyncMock()
    await commands.error_handler(object(), context)
    context.bot.send_message.assert_not_awaited()  # no crash, no send


@pytest.mark.asyncio
async def test_error_handler_clips_long_report(context: MagicMock) -> None:
    commands.configure(settings=_settings(developer_chat_id=42, max_error_chars=100))
    context.error = RuntimeError("x" * 10000)
    context.bot.send_message = AsyncMock()
    await commands.error_handler(object(), context)
    sent_text = context.bot.send_message.call_args.kwargs["text"]
    assert len(sent_text) <= 100

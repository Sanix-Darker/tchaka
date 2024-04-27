from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from telegram import Message, Update, User
from telegram.ext import ContextTypes

from tchaka.commands import start_callback, help_callback, echo_callback


@pytest.fixture
def update() -> Update:
    uu = MagicMock(spec=Update)

    update_user = MagicMock(spec=User)
    update_user.language_code = "en"

    uupdate_message = MagicMock(spec=Message)
    uu.effective_user = update_user
    uu.message = uupdate_message
    return uu


@pytest.fixture
def context():
    return MagicMock(spec=ContextTypes.DEFAULT_TYPE)


@pytest.mark.anyio
async def test_start_callback(update, context):
    update.message.chat_id = 123
    update.effective_user.full_name = "John Doe"
    message = update.message.reply_text = AsyncMock()
    await start_callback(update, context)
    message.assert_called_once_with(text=ANY)


@pytest.mark.anyio
async def test_help_callback(update, context):
    update.message.chat_id = 123
    update.effective_user.full_name = "John Doe"
    message = update.message.reply_text = AsyncMock()
    await help_callback(update, context)
    message.assert_called_once_with(text=ANY)


@pytest.mark.anyio
async def test_echo_callback(update, context):
    update.message.chat_id = 123
    update.effective_user.full_name = "John Doe"
    update.message.text = "This is a test message"
    await echo_callback(
        update, context
    )  # no errors for now, tests are going to be defined soon or later

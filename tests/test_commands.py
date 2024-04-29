from unittest.mock import ANY, AsyncMock, MagicMock
from pytest_mock import MockerFixture
import pytest
from telegram import Message, Update, User
from telegram.ext import ContextTypes
from tchaka import commands as tchaka_commands_module

from tchaka.commands import append_chat_ids_messages, start_callback, help_callback, echo_callback


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
async def test_start_callback(
    mocker: MockerFixture, update: MagicMock, context: ContextTypes.DEFAULT_TYPE
) -> None:
    mocker.patch("tchaka.commands.append_chat_ids_messages")
    update.message.chat_id = 123
    update.effective_user.full_name = "John Doe"
    message = update.message.reply_text = AsyncMock()
    await start_callback(update, context)
    message.assert_called_once_with(text=ANY)


@pytest.mark.anyio
async def test_help_callback(
    mocker: MockerFixture, update: MagicMock, context: ContextTypes.DEFAULT_TYPE
) -> None:
    mocker.patch("tchaka.commands.append_chat_ids_messages")
    update.message.chat_id = 123
    update.effective_user.full_name = "John Doe"
    message = update.message.reply_text = AsyncMock()
    await help_callback(update, context)
    message.assert_called_once_with(text=ANY)


@pytest.mark.anyio
async def test_echo_callback(
    update: MagicMock,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    update.message.chat_id = 123
    update.effective_user.full_name = "John Doe"
    update.message.text = "This is a test message"
    await echo_callback(
        update, context
    )  # no errors for now, tests are going to be defined soon or later

@pytest.mark.anyio
async def test_attach_chat_id_to_message_ids(mocker: MockerFixture) -> None:
    await append_chat_ids_messages(1, 34)
    await append_chat_ids_messages(10, 234)

    id_msgs = await append_chat_ids_messages(1, 40)
    assert id_msgs == {1: [34, 35, 36, 37, 38, 39, 40], 10: [234]}

from unittest.mock import MagicMock

import pytest
from telegram import Update, Message, User

from tchaka.utils import safe_truncate, get_user_and_message


@pytest.fixture
def update() -> Update:
    uu = MagicMock(spec=Update)

    update_user = MagicMock(spec=User)
    update_user.language_code = "en"

    uupdate_message = MagicMock(spec=Message)
    uu.effective_user = update_user
    uu.message = uupdate_message
    return uu


@pytest.mark.anyio
async def test_safe_truncate():
    message = "This is a test message"
    truncated_message = safe_truncate(message, 10)
    assert truncated_message == "This is a "


@pytest.mark.anyio
async def test_safe_truncate_with_none():
    assert safe_truncate(None) == ""


@pytest.mark.anyio
async def test_get_user_and_message(update):
    user = MagicMock(spec=User)
    message = MagicMock(spec=Message)
    update.effective_user = user
    update.message = message

    result_user, result_message = await get_user_and_message(update)
    assert result_user == user
    assert result_message == message


@pytest.mark.anyio
async def test_get_user_and_message_with_none_user(update):
    update.effective_user = None
    update.message = MagicMock(spec=Message)

    with pytest.raises(Exception):
        await get_user_and_message(update)


@pytest.mark.anyio
async def test_get_user_and_message_with_none_message(update):
    update.effective_user = MagicMock(spec=User)
    update.message = None

    with pytest.raises(Exception):
        await get_user_and_message(update)


@pytest.mark.anyio
async def test_get_user_and_message_with_bot(update):
    user = MagicMock(spec=User)
    user.is_bot = True
    update.effective_user = user
    update.message = MagicMock(spec=Message)

    with pytest.raises(Exception):
        await get_user_and_message(update)

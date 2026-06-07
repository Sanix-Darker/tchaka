from unittest.mock import MagicMock

import pytest
from hypothesis import given
from hypothesis import strategies as st
from telegram import Message, Update, User

from tchaka.utils import (
    FakeClock,
    SystemClock,
    build_user_hash,
    get_user_and_message,
    safe_truncate,
)


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
    truncated_message = safe_truncate(message, 3)
    assert truncated_message == "Thi..."

    # No troncate nor points
    truncated_message = safe_truncate(message, 100)
    assert truncated_message == "This is a test message"


@pytest.mark.anyio
async def test_safe_truncate_with_none():
    assert safe_truncate(None) == ""


@given(s=st.text(), n=st.integers(min_value=0, max_value=2000))
def test_safe_truncate_length_bound(s: str, n: int) -> None:
    # P-MSG-3: result never exceeds n + len("...").
    out = safe_truncate(s, n)
    assert len(out) <= n + 3


@given(s=st.text(min_size=0, max_size=500), n=st.integers(min_value=0, max_value=600))
def test_safe_truncate_prefix_and_identity(s: str, n: int) -> None:
    # P-MSG-4: output starts with s[:n]; equals s when it already fits.
    out = safe_truncate(s, n)
    assert out.startswith(s[:n])
    if len(s) <= n:
        assert out == s


@pytest.mark.anyio
async def test_get_user_and_message(update):
    user = MagicMock(spec=User)
    user.is_bot = False
    message = MagicMock(spec=Message)
    update.effective_user = user
    update.message = message

    result_user, result_message = await get_user_and_message(update)
    assert result_user == user
    assert result_message == message


@pytest.mark.anyio
async def test_get_user_and_message_recomputes(update):
    # Regression for the removed @lru_cache: a second call with mutated state
    # must reflect the new state, not a cached result.
    user = MagicMock(spec=User)
    user.is_bot = False
    update.effective_user = user
    update.message = MagicMock(spec=Message)
    u1, _ = await get_user_and_message(update)

    new_user = MagicMock(spec=User)
    new_user.is_bot = False
    update.effective_user = new_user
    u2, _ = await get_user_and_message(update)

    assert u1 is user
    assert u2 is new_user


@pytest.mark.anyio
async def test_get_user_and_message_with_none_user(update):
    update.effective_user = None
    update.message = MagicMock(spec=Message)

    with pytest.raises(ValueError):
        await get_user_and_message(update)


@pytest.mark.anyio
async def test_get_user_and_message_with_none_message(update):
    update.effective_user = MagicMock(spec=User)
    update.message = None

    with pytest.raises(ValueError):
        await get_user_and_message(update)


@pytest.mark.anyio
async def test_get_user_and_message_with_bot(update):
    user = MagicMock(spec=User)
    user.is_bot = True
    update.effective_user = user
    update.message = MagicMock(spec=Message)

    with pytest.raises(ValueError):
        await get_user_and_message(update)


@pytest.mark.anyio
async def test_build_user_hash_shape():
    h = await build_user_hash("John Doe")
    assert h.startswith("u")
    assert len(h) == 6


@pytest.mark.anyio
async def test_build_user_hash_salted_uniqueness():
    # The random salt makes repeated hashes of the same name differ (unlinkable).
    a = await build_user_hash("John Doe")
    b = await build_user_hash("John Doe")
    assert a != b


def test_fake_clock_advance():
    clk = FakeClock(100.0)
    assert clk.now() == 100.0
    clk.advance(50.0)
    assert clk.now() == 150.0


def test_system_clock_monotone_ish():
    clk = SystemClock()
    assert isinstance(clk.now(), float)
    assert clk.now() > 0

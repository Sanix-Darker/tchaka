"""Tests for the domain layer (tchaka.core) and pure geo helpers.

Covers worked examples and mock-bot async behavior:
- haversine known distances
- count_nearby / neighbors worked example
- relay_message: same-radius-only, never the sender (P-MSG-1, P-MSG-2)
- notify_group_join: only neighbors get notified (Issue #6 regression)
- evict_idle_users with FakeClock (P-ST-4, P-TRK-3)
- cleanup_messages deletes only tracked ids (no fabrication, P-TRK-1)
- format_relay_body never leaks chat_id / full name (P-ID-1)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture

from tchaka.core import (
    cleanup_messages,
    count_nearby,
    evict_idle_users,
    format_relay_body,
    haversine_distance,
    notify_group_join,
    register_user,
    relay_message,
)
from tchaka.state import AppState, Coord, UserRecord
from tchaka.utils import FakeClock


@pytest.mark.parametrize(
    "lat1, lon1, lat2, lon2, expected_distance",
    [
        (52.5200, 13.4050, 52.5201, 13.4051, 0.013),
        (52.5200, 13.4050, 52.5205, 13.4055, 0.065),
        (52.5200, 13.4050, 52.5210, 13.4060, 0.13),
    ],
)
def test_haversine_distance(lat1, lon1, lat2, lon2, expected_distance):
    assert round(haversine_distance(lat1, lon1, lat2, lon2), 3) == expected_distance


def _seed(state: AppState, uid: str, chat_id: int, lat: float, lon: float) -> None:
    state.register(
        UserRecord(
            user_id=uid, chat_id=chat_id, coord=Coord(lat, lon), last_active_ts=0.0
        )
    )


def test_count_nearby_excludes_self_and_respects_radius():
    state = AppState()
    # Berlin cluster (very close together) + far away point.
    _seed(state, "a", 1, 52.5200, 13.4050)
    _seed(state, "b", 2, 52.5201, 13.4051)  # ~13 m from a
    _seed(state, "c", 3, 48.8566, 2.3522)  # Paris, ~880 km
    assert count_nearby(state, "a", threshold_km=5.0) == 1  # only b
    assert count_nearby(state, "a", threshold_km=2000.0) == 2  # b and c
    assert count_nearby(state, "c", threshold_km=5.0) == 0  # alone


def test_register_user_no_float_keys():
    state = AppState()
    rec = register_user(
        state,
        user_id="u1",
        chat_id=42,
        coord=Coord(10.0, 20.0),
        lang="en",
        clock=FakeClock(5.0),
    )
    assert rec.last_active_ts == 5.0
    assert state.users["u1"] is rec
    assert state.chat_to_user[42] == "u1"
    # keys are user_id (str) and chat_id (int); no tuple/float keys anywhere
    assert all(isinstance(k, str) for k in state.users)
    assert all(isinstance(k, int) for k in state.chat_to_user)


def test_format_relay_body_no_pii():
    body = format_relay_body("uABCDE", "hello world", max_chars=500)
    assert "uABCDE" in body
    assert "hello world" in body
    # No chat id or full name leaks.
    assert "12345" not in body
    assert "John" not in body


def test_format_relay_body_truncates():
    long_text = "x" * 1000
    body = format_relay_body("uABCDE", long_text, max_chars=100)
    # body = header + truncated(<=103). Truncated portion must be bounded.
    assert "x" * 100 in body
    assert "x" * 200 not in body


@pytest.mark.asyncio
async def test_relay_only_to_snapshot_recipients():
    ctx_bot = AsyncMock()
    ctx_bot.send_message = AsyncMock(return_value=type("M", (), {"message_id": 99})())
    state = AppState()
    await relay_message(ctx_bot, state, body="hi", recipients_snapshot=[111, 222])
    assert ctx_bot.send_message.await_count == 2
    sent_chat_ids = {c.kwargs["chat_id"] for c in ctx_bot.send_message.await_args_list}
    assert sent_chat_ids == {111, 222}
    # real returned ids tracked, none fabricated
    assert state.tracked_msgs[111] == {99}
    assert state.tracked_msgs[222] == {99}


@pytest.mark.asyncio
async def test_relay_never_to_sender_via_neighbors_snapshot():
    # Build recipients from neighbors (which excludes the sender), prove sender
    # chat id is absent. P-MSG-1 / P-MSG-2.
    state = AppState()
    _seed(state, "sender", 1, 52.5200, 13.4050)
    _seed(state, "near", 2, 52.5201, 13.4051)
    _seed(state, "far", 3, 48.8566, 2.3522)
    neighbors = state.neighbors("sender", 5.0)
    recipients = [n.chat_id for n in neighbors]
    assert recipients == [2]  # only the near user; not sender (1), not far (3)

    ctx_bot = AsyncMock()
    ctx_bot.send_message = AsyncMock(return_value=type("M", (), {"message_id": 7})())
    await relay_message(ctx_bot, state, body="hello", recipients_snapshot=recipients)
    sent_chat_ids = {c.kwargs["chat_id"] for c in ctx_bot.send_message.await_args_list}
    assert 1 not in sent_chat_ids  # never the sender


@pytest.mark.asyncio
async def test_notify_group_join_only_neighbors():
    # Issue #6 regression: only same-radius neighbors get the join ping.
    state = AppState()
    new_rec = UserRecord("new", 1, Coord(52.5200, 13.4050), 0.0)
    state.register(new_rec)
    _seed(state, "near", 2, 52.5201, 13.4051)
    _seed(state, "far", 3, 48.8566, 2.3522)
    recipients = [n.chat_id for n in state.neighbors("new", 5.0)]
    assert recipients == [2]

    ctx_bot = AsyncMock()
    ctx_bot.send_message = AsyncMock(return_value=type("M", (), {"message_id": 5})())
    await notify_group_join(
        ctx_bot, state, new_user=new_rec, recipients_snapshot=recipients
    )
    sent_chat_ids = {c.kwargs["chat_id"] for c in ctx_bot.send_message.await_args_list}
    assert sent_chat_ids == {2}  # not 1 (self), not 3 (far)


@pytest.mark.asyncio
async def test_evict_idle_users_removes_only_idle():
    state = AppState()
    clock = FakeClock(0.0)
    register_user(
        state,
        user_id="active",
        chat_id=1,
        coord=Coord(0.0, 0.0),
        lang="en",
        clock=clock,
    )
    register_user(
        state, user_id="idle", chat_id=2, coord=Coord(0.0, 0.0), lang="en", clock=clock
    )
    state.track_message(2, 100)
    state.track_message(2, 101)

    # advance 2h; touch only the active user
    clock.advance(7200)
    state.touch("active", clock.now())

    ctx_bot = AsyncMock()
    ctx_bot.delete_message = AsyncMock()
    evicted = await evict_idle_users(ctx_bot, state, now=clock.now(), ttl=3600)

    assert evicted == ["idle"]
    assert "idle" not in state.users
    assert 2 not in state.chat_to_user
    assert 2 not in state.tracked_msgs
    assert "active" in state.users  # P-ST-5: active survives
    # deleted only the idle user's tracked ids (P-TRK-3)
    deleted = {c.kwargs["message_id"] for c in ctx_bot.delete_message.await_args_list}
    assert deleted == {100, 101}


@pytest.mark.asyncio
async def test_cleanup_messages_only_tracked_ids():
    ctx_bot = AsyncMock()
    ctx_bot.delete_message = AsyncMock()
    await cleanup_messages(ctx_bot, 42, {10, 11, 12})
    deleted = {c.kwargs["message_id"] for c in ctx_bot.delete_message.await_args_list}
    assert deleted == {10, 11, 12}


@pytest.mark.asyncio
async def test_cleanup_messages_empty_noop():
    ctx_bot = AsyncMock()
    ctx_bot.delete_message = AsyncMock()
    await cleanup_messages(ctx_bot, 42, None)
    await cleanup_messages(ctx_bot, 42, set())
    ctx_bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_relay_skips_blocked_recipient(mocker: MockerFixture):
    from telegram.error import Forbidden

    state = AppState()

    async def _send(*args, **kwargs):
        if kwargs["chat_id"] == 111:
            raise Forbidden("blocked")
        return type("M", (), {"message_id": 9})()

    ctx_bot = AsyncMock()
    ctx_bot.send_message = AsyncMock(side_effect=_send)
    await relay_message(ctx_bot, state, body="hi", recipients_snapshot=[111, 222])
    # 222 still tracked despite 111 failing
    assert state.tracked_msgs.get(222) == {9}
    assert 111 not in state.tracked_msgs

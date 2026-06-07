"""Domain operations for tchaka.

This layer sits between the typed state (:mod:`tchaka.state`) and the Telegram
callbacks (:mod:`tchaka.commands`). It contains the decision logic for user
registration, neighbor counting, join notification, message relay, message
cleanup, and idle eviction.

Concurrency rules (see design "Concurrency Model"):
- Every read-modify-write on :class:`AppState` happens while holding
  ``state.lock``.
- Network I/O is **never** performed while holding the lock. Callers snapshot
  the recipient list under the lock, release it, send, then briefly re-acquire
  to track the real returned message ids.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

# Re-export the pure geo helpers so existing imports keep working.
from tchaka.geo import EARTH_RADIUS_KM, group_coordinates, haversine_distance
from tchaka.state import AppState, Coord, UserRecord
from tchaka.utils import Clock, html_format_text, safe_truncate

if TYPE_CHECKING:
    from telegram import Bot, Message

__all__ = [
    "EARTH_RADIUS_KM",
    "haversine_distance",
    "group_coordinates",
    "count_nearby",
    "register_user",
    "notify_group_join",
    "relay_message",
    "cleanup_messages",
    "evict_idle_users",
    "format_relay_body",
]

_LOGGER = logging.getLogger(__name__)
MAX_BAD_REQUEST_ERROR = 10


# --------------------------------------------------------------------------- #
# Neighborhood / counting
# --------------------------------------------------------------------------- #
def count_nearby(state: AppState, user_id: str, threshold_km: float) -> int:
    """Number of OTHER users within ``threshold_km`` of ``user_id``. Excludes
    the requesting user."""
    return len(state.neighbors(user_id, threshold_km))


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
def register_user(
    state: AppState,
    *,
    user_id: str,
    chat_id: int,
    coord: Coord,
    lang: str,
    clock: Clock,
) -> UserRecord:
    """Insert a typed user record (caller holds ``state.lock``).

    No float coordinate is ever used as a key; the coordinate lives inside the
    record only.
    """
    rec = UserRecord(
        user_id=user_id,
        chat_id=chat_id,
        coord=coord,
        last_active_ts=clock.now(),
        lang=lang,
    )
    state.register(rec)
    return rec


# --------------------------------------------------------------------------- #
# Message formatting
# --------------------------------------------------------------------------- #
def format_relay_body(
    sender_user_id: str,
    text: str | None,
    max_chars: int,
    reply_excerpt: tuple[str, str] | None = None,
) -> str:
    """Build the outgoing relay text.

    Contains only the sender's anonymized ``user_id`` -- never the sender's
    chat id or full name (anonymity property P-ID-1).
    """
    truncated = safe_truncate(text, max_chars)
    if reply_excerpt is not None:
        quote_author, quote_msg = reply_excerpt
        return f"__**{sender_user_id}**__\n```{quote_author}{quote_msg}```\n{truncated}"
    return f"__**{sender_user_id}**__\n\n{truncated}"


# --------------------------------------------------------------------------- #
# Join notification (same-radius neighbors only -- fixes Issue #6)
# --------------------------------------------------------------------------- #
async def notify_group_join(
    bot: Bot,
    state: AppState,
    *,
    new_user: UserRecord,
    recipients_snapshot: list[int],
) -> None:
    """Notify ONLY the chat ids in ``recipients_snapshot`` that a new user
    joined.

    ``recipients_snapshot`` must have been built under the lock and must
    contain only neighbors within range of ``new_user`` and must exclude the
    new user's own chat id.
    """
    text = html_format_text(f"{new_user.user_id} joined the area...")

    async def _send(chat_id: int) -> None:
        try:
            sent = await bot.send_message(
                chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN
            )
            async with state.lock:
                state.track_message(chat_id, sent.message_id)
        except (Forbidden, BadRequest):
            _LOGGER.debug("join notify failed for chat_id=%s", chat_id)
        except Exception:
            _LOGGER.exception("unexpected error notifying chat_id=%s", chat_id)

    await asyncio.gather(*(_send(cid) for cid in recipients_snapshot))


# --------------------------------------------------------------------------- #
# Message relay (same-radius neighbors only, never the sender)
# --------------------------------------------------------------------------- #
async def relay_message(
    bot: Bot,
    state: AppState,
    *,
    body: str,
    recipients_snapshot: list[int],
) -> None:
    """Deliver ``body`` to each chat id in ``recipients_snapshot``.

    The snapshot excludes the sender by construction. Only message ids actually
    returned by Telegram are tracked (no fabricated ids -- fixes Issue #7).
    """

    async def _send(chat_id: int) -> None:
        try:
            sent = await bot.send_message(
                chat_id=chat_id, text=body, parse_mode=ParseMode.MARKDOWN
            )
            async with state.lock:
                state.track_message(chat_id, sent.message_id)
        except (Forbidden, BadRequest):
            _LOGGER.debug("relay failed for chat_id=%s", chat_id)
        except Exception:
            _LOGGER.exception("unexpected error relaying to chat_id=%s", chat_id)

    await asyncio.gather(*(_send(cid) for cid in recipients_snapshot))


# --------------------------------------------------------------------------- #
# Message cleanup (only real, tracked ids -- fixes Issue #7)
# --------------------------------------------------------------------------- #
async def cleanup_messages(
    bot: Bot,
    chat_id: int,
    msg_ids: set[int] | list[int] | None,
) -> None:
    """Best-effort deletion of the given *real* tracked message ids."""
    if not msg_ids:
        return

    consecutive_bad = 0
    for mid in sorted(msg_ids):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
            consecutive_bad = 0
        except BadRequest:
            consecutive_bad += 1
            if consecutive_bad >= MAX_BAD_REQUEST_ERROR:
                break
        except Forbidden:
            break  # user blocked the bot; stop trying
        except Exception:
            _LOGGER.exception("Deletion failed for %s", mid)
            break
        await asyncio.sleep(0.05)  # gentle rate limit


# --------------------------------------------------------------------------- #
# Idle eviction (Issue #2)
# --------------------------------------------------------------------------- #
async def evict_idle_users(
    bot: Bot,
    state: AppState,
    *,
    now: float,
    ttl: float,
) -> list[str]:
    """Evict every user idle for at least ``ttl`` seconds as of ``now``.

    Phase 1 (under lock): identify idle users, remove them fully from state,
    and collect their tracked message ids. Phase 2 (no lock): best-effort
    delete those messages. Returns the list of evicted user ids.
    """
    to_clean: list[tuple[int, set[int]]] = []
    evicted: list[str] = []

    async with state.lock:
        idle_ids = state.idle_user_ids(now, ttl)
        for uid in idle_ids:
            rec = state.users.get(uid)
            if rec is None:
                continue
            state.remove_by_chat(rec.chat_id)
            msg_ids = state.pop_tracked(rec.chat_id)
            to_clean.append((rec.chat_id, msg_ids))
            evicted.append(uid)

    for chat_id, msg_ids in to_clean:
        await cleanup_messages(bot, chat_id, msg_ids)

    return evicted


# --------------------------------------------------------------------------- #
# Helper to build a reply excerpt from a replied-to message
# --------------------------------------------------------------------------- #
def build_reply_excerpt(message: Message) -> tuple[str, str] | None:
    """Extract a (author, excerpt) tuple from a replied-to message, if any."""
    replied = message.reply_to_message
    if replied is not None and replied.text:
        lines = replied.text.splitlines()
        if lines:
            return lines[0], safe_truncate(lines[-1])
    return None

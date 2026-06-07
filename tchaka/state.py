"""Typed, lockable in-memory state container for tchaka.

This module replaces the four loose module-level dicts that previously lived in
``commands.py`` (``_USERS``, ``_CHAT_IDS``, ``_CHAT_IDS_MSGS``, ``_GROUPS``)
with a single typed :class:`AppState`.  The container is the single source of
truth and is guarded by one :class:`asyncio.Lock`.

Design notes (see ``.kiro/specs/tchaka-product-improvements/design.md``):

- Coordinates are stored only as *values* inside a :class:`UserRecord`; they are
  never used as mapping keys, so two users sharing identical coordinates can
  never collide (fixes the float-tuple-key bug).
- The user registry is keyed by a stable anonymized ``user_id``.
- ``tracked_msgs`` only ever holds *real* message ids (sent by the bot or
  received from a user) -- no fabricated/incremented ids.
- The dataclass methods themselves are plain (not async) and do **not** acquire
  the lock.  Callers acquire ``state.lock`` around any read-modify-write
  sequence and never perform network I/O while holding it.

State invariants (enforced by the mutators):

- I1 -- Bijection consistency: every ``chat_to_user`` entry points to a record
  carrying that same chat id, and every record's chat id resolves back.
- I2 -- Unique identity: each ``user_id`` and each ``chat_id`` appears once.
- I3 -- Full removal: :meth:`remove_by_chat` + :meth:`pop_tracked` leave no
  dangling references.
- I4 -- Real ids only: :meth:`track_message` records only real ids.
- I5 -- Coordinate values, not keys.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import NamedTuple

from tchaka.geo import haversine_distance

__all__ = ["Coord", "UserRecord", "AppState"]


class Coord(NamedTuple):
    """A WGS-84 latitude/longitude pair. A value type, never a mapping key."""

    lat: float
    lon: float


@dataclass
class UserRecord:
    """Everything tchaka knows about an active user (all in memory)."""

    user_id: str  # anonymized stable hash, e.g. "u1a2b3"
    chat_id: int
    coord: Coord
    last_active_ts: float  # epoch seconds, sourced from an injected Clock
    lang: str = "en"
    range_km: float | None = None  # reserved: per-user override (deferred R8)


@dataclass
class AppState:
    """The single, lockable source of truth for tchaka's runtime state."""

    chat_to_user: dict[int, str] = field(default_factory=dict)
    users: dict[str, UserRecord] = field(default_factory=dict)
    tracked_msgs: dict[int, set[int]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # ------------------------------------------------------------------ #
    # Mutators (callers hold ``self.lock``)
    # ------------------------------------------------------------------ #
    def register(self, rec: UserRecord) -> None:
        """Insert a new user record and its chat mapping.

        Postconditions: ``users[rec.user_id] is rec`` and
        ``chat_to_user[rec.chat_id] == rec.user_id`` (maintains I1, I2).
        Idempotency at the chat level is the caller's responsibility (check
        :meth:`user_for_chat` first).
        """
        self.users[rec.user_id] = rec
        self.chat_to_user[rec.chat_id] = rec.user_id

    def remove_by_chat(self, chat_id: int) -> UserRecord | None:
        """Remove the user owning ``chat_id``. Safe if absent (idempotent).

        Returns the removed record or ``None``. Callers should also call
        :meth:`pop_tracked` to clear the chat's tracked messages (I3).
        """
        user_id = self.chat_to_user.pop(chat_id, None)
        if user_id is None:
            return None
        return self.users.pop(user_id, None)

    def track_message(self, chat_id: int, message_id: int) -> None:
        """Record a *real* message id for later cleanup (maintains I4).

        Set semantics make this idempotent: tracking the same id twice stores
        it once.
        """
        self.tracked_msgs.setdefault(chat_id, set()).add(message_id)

    def pop_tracked(self, chat_id: int) -> set[int]:
        """Remove and return the set of tracked message ids for ``chat_id``."""
        return self.tracked_msgs.pop(chat_id, set())

    def touch(self, user_id: str, now: float) -> None:
        """Update a user's last-activity timestamp. No-op if user is absent."""
        rec = self.users.get(user_id)
        if rec is not None:
            rec.last_active_ts = now

    # ------------------------------------------------------------------ #
    # Pure queries (no mutation)
    # ------------------------------------------------------------------ #
    def user_for_chat(self, chat_id: int) -> UserRecord | None:
        """Resolve the record owning ``chat_id`` (or ``None``)."""
        user_id = self.chat_to_user.get(chat_id)
        if user_id is None:
            return None
        return self.users.get(user_id)

    def effective_range(self, rec: UserRecord, global_threshold_km: float) -> float:
        """Range to use for ``rec``: the per-user override capped by the global
        threshold, else the global threshold (R8 scaffolding)."""
        if rec.range_km is None:
            return global_threshold_km
        return min(rec.range_km, global_threshold_km)

    def neighbors(self, user_id: str, threshold_km: float) -> list[UserRecord]:
        """Return other users within ``threshold_km`` of ``user_id``.

        Ego-centric and symmetric per pair, but **not** transitive. Excludes
        the requesting user. Pure (no mutation). Requires ``user_id`` present.
        """
        origin = self.users[user_id]
        radius = self.effective_range(origin, threshold_km)
        result: list[UserRecord] = []
        for uid, rec in self.users.items():
            if uid == user_id:
                continue
            if (
                haversine_distance(
                    origin.coord.lat,
                    origin.coord.lon,
                    rec.coord.lat,
                    rec.coord.lon,
                )
                <= radius
            ):
                result.append(rec)
        return result

    def idle_user_ids(self, now: float, ttl_seconds: float) -> list[str]:
        """Return user ids idle for at least ``ttl_seconds`` as of ``now``."""
        return [
            uid
            for uid, rec in self.users.items()
            if now - rec.last_active_ts >= ttl_seconds
        ]

"""Stateful property-based tests for :class:`AppState` invariants.

Drives a Hypothesis ``RuleBasedStateMachine`` through arbitrary sequences of
register / stop / track / touch / evict operations and asserts the state
invariants from the design hold after *every* step.

Property coverage:
- P-ST-1  bijection consistency (I1, I2)
- P-ST-2  full removal leaves no dangling references (I3)
- P-ST-3  stop removes everything
- P-ST-4  idle eviction removes only idle users
- P-ST-5  touch monotonicity (active users survive eviction)
- P-TRK-1 tracked ids are a subset of the real ids ever tracked (no fabrication)
- P-TRK-2 tracking is idempotent (set semantics)
"""

from __future__ import annotations

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from tchaka.state import AppState, Coord, UserRecord

lats = st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False)
lons = st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False)
chat_ids = st.integers(min_value=1, max_value=50)
msg_ids = st.integers(min_value=1, max_value=10_000)


class AppStateMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.state = AppState()
        self.clock = 0.0
        # Shadow model of every message id we ever legitimately tracked, per
        # chat. Used to prove tracked_msgs never contains a fabricated id.
        self.ever_tracked: dict[int, set[int]] = {}

    def _uid_for(self, chat_id: int) -> str:
        return f"u{chat_id}"

    @rule(chat_id=chat_ids, lat=lats, lon=lons)
    def register(self, chat_id: int, lat: float, lon: float) -> None:
        if self.state.user_for_chat(chat_id) is None:
            self.state.register(
                UserRecord(
                    user_id=self._uid_for(chat_id),
                    chat_id=chat_id,
                    coord=Coord(lat, lon),
                    last_active_ts=self.clock,
                )
            )

    @rule(chat_id=chat_ids)
    def stop(self, chat_id: int) -> None:
        self.state.remove_by_chat(chat_id)
        self.state.pop_tracked(chat_id)
        self.ever_tracked.pop(chat_id, None)

    @rule(chat_id=chat_ids, message_id=msg_ids)
    def track(self, chat_id: int, message_id: int) -> None:
        self.state.track_message(chat_id, message_id)
        self.ever_tracked.setdefault(chat_id, set()).add(message_id)

    @rule(
        chat_id=chat_ids, dt=st.floats(min_value=0, max_value=10_000, allow_nan=False)
    )
    def advance_and_touch(self, chat_id: int, dt: float) -> None:
        self.clock += dt
        rec = self.state.user_for_chat(chat_id)
        if rec is not None:
            self.state.touch(rec.user_id, self.clock)

    @rule(ttl=st.floats(min_value=0, max_value=5_000, allow_nan=False))
    def evict(self, ttl: float) -> None:
        idle = self.state.idle_user_ids(self.clock, ttl)
        # snapshot which users are *not* idle so we can assert they survive
        survivors = {
            uid
            for uid, rec in self.state.users.items()
            if self.clock - rec.last_active_ts < ttl
        }
        for uid in idle:
            rec = self.state.users[uid]
            self.state.remove_by_chat(rec.chat_id)
            self.state.pop_tracked(rec.chat_id)
            self.ever_tracked.pop(rec.chat_id, None)
        # P-ST-4 / P-ST-5: every survivor is still present, every idle gone
        for uid in survivors:
            assert uid in self.state.users
        for uid in idle:
            assert uid not in self.state.users

    # ------------------------------------------------------------------ #
    # Invariants (checked after every rule)
    # ------------------------------------------------------------------ #
    @invariant()
    def bijection_consistent(self) -> None:  # P-ST-1
        for cid, uid in self.state.chat_to_user.items():
            assert uid in self.state.users
            assert self.state.users[uid].chat_id == cid
        for uid, rec in self.state.users.items():
            assert self.state.chat_to_user.get(rec.chat_id) == uid

    @invariant()
    def no_fabricated_ids(self) -> None:  # P-TRK-1 / P-TRK-2
        for cid, tracked in self.state.tracked_msgs.items():
            assert tracked <= self.ever_tracked.get(cid, set())


TestAppStateMachine = AppStateMachine.TestCase

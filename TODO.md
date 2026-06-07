## TODO

- [ ] Add more screenshots in the README of the running app.
- [x] Check how many people are around (the `/check` command is implemented).
- [x] Handle the 'smart' auto clean of user after inactivity (idle eviction,
      configurable via `TCHAKA_IDLE_TTL_SECONDS`, sweeps every
      `TCHAKA_SWEEP_INTERVAL_SECONDS`).
- [x] Configuration of the range (`TCHAKA_RANGE_KM`, default 5 km). Per-user
      override is scaffolded in the data model (`UserRecord.range_km`) but the
      `/range` command is not shipped yet.
- [ ] Play Games with people around you?

## Done (product hardening)

- Replaced the four loose global dicts with a single typed, lockable
  `AppState` (see `tchaka/state.py`).
- Ego-centric, non-transitive "people around you" model (fixes the union-find
  chaining issue); join notifications and message relay target only users
  within range and never the sender.
- Message-id tracking now records only real ids (no fabricated/incremented
  ids); cleanup deletes only tracked ids.
- Removed the broken `@lru_cache` on the async `get_user_and_message`.
- Hardened the error handler: no hard assert on a missing `DEVELOPER_CHAT_ID`,
  reports clipped below Telegram's 4096-char limit, and a failing report send
  no longer crashes the handler.
- The "tchaka started successfully" log is now emitted at startup (via a
  `post_init` hook) instead of after the blocking `run_polling`.
- Extensive property-based tests (Hypothesis) for the geospatial, neighborhood,
  state-invariant, relay, and message-id behaviors.

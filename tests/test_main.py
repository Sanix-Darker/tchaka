"""Tests for the entrypoint wiring (tchaka.main).

Verifies the startup-ordering fix (Issue #4): the success log and the idle-job
scheduling happen in ``post_init`` -- before the blocking ``run_polling`` -- so
they actually run at startup.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

import tchaka.commands as commands
from tchaka.config import Settings
from tchaka.main import HANDLERS, idle_job
from tchaka.state import AppState, Coord, UserRecord
from tchaka.utils import FakeClock


def _settings() -> Settings:
    return Settings(
        tg_token="tok",
        developer_chat_id=None,
        distance_threshold_km=5.0,
        idle_ttl_seconds=3600,
        sweep_interval_seconds=300,
        max_relay_chars=500,
        max_error_chars=3500,
    )


def test_handlers_registered() -> None:
    # start, stop, check, help, location, echo
    assert len(HANDLERS) == 6


@pytest.mark.asyncio
async def test_idle_job_evicts_idle_users() -> None:
    state = AppState()
    clock = FakeClock(0.0)
    commands.configure(state=state, settings=_settings(), clock=clock)
    state.register(UserRecord("idle", 1, Coord(0.0, 0.0), last_active_ts=0.0))
    state.register(UserRecord("active", 2, Coord(0.0, 0.0), last_active_ts=0.0))

    clock.advance(7200)  # 2h
    state.touch("active", clock.now())

    ctx = MagicMock()
    ctx.bot = AsyncMock()
    await idle_job(ctx)

    assert "idle" not in state.users
    assert "active" in state.users


@pytest.mark.asyncio
async def test_post_init_logs_and_schedules(
    caplog: pytest.LogCaptureFixture, mocker
) -> None:
    # Capture the REAL post_init closure that build_application registers, then
    # invoke it against a fake application to assert scheduling + logging.
    from tchaka import main as main_module

    state = AppState()
    settings = _settings()

    captured: dict = {}

    class FakeJobQueue:
        def run_repeating(self, cb, interval, first):  # noqa: ANN001
            captured["interval"] = interval
            captured["first"] = first
            captured["cb"] = cb

    class FakeApp:
        job_queue = FakeJobQueue()

        def add_handler(self, handler):  # noqa: ANN001
            pass

        def add_error_handler(self, handler):  # noqa: ANN001
            pass

    class FakeBuilder:
        def token(self, _tok):  # noqa: ANN001
            return self

        def post_init(self, hook):  # noqa: ANN001
            captured["post_init"] = hook
            return self

        def build(self):
            return FakeApp()

    mocker.patch.object(
        main_module.Application, "builder", staticmethod(lambda: FakeBuilder())
    )

    app = main_module.build_application(settings, state, FakeClock(0.0))
    assert app is not None
    assert "post_init" in captured

    with caplog.at_level(logging.INFO, logger="tchaka.main"):
        await captured["post_init"](FakeApp())

    assert captured["interval"] == settings.sweep_interval_seconds
    assert captured["first"] == settings.sweep_interval_seconds
    assert any("started successfully" in r.message for r in caplog.records)

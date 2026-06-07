"""tchaka entrypoint.

Builds the Telegram ``Application``, wires the runtime singletons into the
callback module, schedules the idle-eviction job, emits the startup-success log
at the right time (via ``post_init`` -- not after the blocking ``run_polling``),
and starts long-polling.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import tchaka.commands as commands
from tchaka.commands import (
    check_callback,
    echo_callback,
    error_handler,
    help_callback,
    location_callback,
    start_callback,
    stop_callback,
)
from tchaka.config import Settings, load_settings
from tchaka.core import evict_idle_users
from tchaka.state import AppState
from tchaka.utils import Clock, SystemClock

_LOGGER = logging.getLogger(__name__)

HANDLERS = [
    CommandHandler("start", start_callback),
    CommandHandler("stop", stop_callback),
    CommandHandler("check", check_callback),
    CommandHandler("help", help_callback),
    MessageHandler(filters.LOCATION, location_callback),
    MessageHandler(filters.TEXT & ~filters.COMMAND, echo_callback),
]


async def idle_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: evict idle users on each sweep."""
    settings = commands.SETTINGS
    if settings is None:
        return
    evicted = await evict_idle_users(
        context.bot,
        commands.STATE,
        now=commands.CLOCK.now(),
        ttl=settings.idle_ttl_seconds,
    )
    if evicted:
        _LOGGER.info("idle sweep evicted %d user(s)", len(evicted))


def build_application(settings: Settings, state: AppState, clock: Clock) -> Application:
    """Build and wire the Telegram application (factory; no polling)."""
    commands.configure(state=state, settings=settings, clock=clock)

    async def _post_init(application: Application) -> None:
        if application.job_queue is not None:
            application.job_queue.run_repeating(
                idle_job,
                interval=settings.sweep_interval_seconds,
                first=settings.sweep_interval_seconds,
            )
        # Emitted at startup (after init), not after the blocking run_polling.
        _LOGGER.info("tchaka started successfully...")

    application = (
        Application.builder().token(settings.tg_token).post_init(_post_init).build()
    )
    for handler in HANDLERS:
        application.add_handler(handler)
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    settings = load_settings()
    state = AppState()
    clock = SystemClock()
    application = build_application(settings, state, clock)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

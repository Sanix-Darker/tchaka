from __future__ import annotations

import html
import logging
import secrets
import time
from hashlib import sha256
from typing import Protocol

from telegram import Message, Update, User

MAX_STR_SENT_BACK = 1000
# We prevent flowing logs from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)


def safe_truncate(message: str | None, at: int = 100) -> str:
    """Truncate ``message`` to at most ``at`` characters, appending an ellipsis
    when truncation occurred. Returns ``""`` for falsy input."""
    if not message:
        return ""

    points = ""
    if len(message) > at:
        points = "..."

    return message[:at] + points


def html_format_text(strr: str) -> str:
    return html.escape(str(safe_truncate(strr, MAX_STR_SENT_BACK)))


async def get_user_and_message(update: Update) -> tuple[User, Message]:
    """Return the effective user and message from an ``update``.

    Recomputed on every call (no caching): an ``Update`` is unhashable and a
    coroutine result cannot be meaningfully memoized, so the previous
    ``@lru_cache`` was both broken and risky.

    Raises ``ValueError`` if either is ``None`` or the sender is a bot.
    """
    if (user := update.effective_user) is None or (message := update.message) is None:
        raise ValueError(f"user or message is None :: {update}")

    if user.is_bot is True:
        raise ValueError(f"bot detected :: {user.full_name=}")

    return user, message


async def build_user_hash(fullname: str) -> str:
    """Build a short, non-reversible anonymized display id for ``fullname``.

    A cryptographically-strong random salt makes the short hash unlinkable
    across sessions (the value is only ever used as a display handle).
    """
    salt = secrets.token_hex(8)
    usr = sha256(f"{fullname}-salt-{salt}".encode()).hexdigest()
    return f"u{usr[:5]}"


def build_welcome_location_message_for_current_user(
    user_new_name: str,
    users_list_count: int,
    lang: str,
) -> str:
    """Build the localized 'location received' message."""

    if lang == "fr":
        suggest_to_connect = (
            (
                f"Il y a ({users_list_count}) personnes dans la meme zone que "
                "vous. ils sont avertis.\n"
                "N'hesitez pas a dire bonjour.\n"
            )
            if users_list_count >= 1
            else ("0 utilisateurs ici pour le moment.\n")
        )
        return (
            f"Localisation reçue !!!\n"
            f"Maintenant, vous etes ***__{user_new_name}__***.\n"
            f"{suggest_to_connect}\n"
            "Remarque : Tout ici est crypte et le chat sera nettoye lorsque vous changerez de lieu.\n\n"
            "Pour toute question, signalez au dev @sanixdarker"
        )

    suggest_to_connect = (
        (
            f"There is ({users_list_count}) people in the same area than "
            "you. They just get notified.\n"
            "Feel free to say hi.\n"
        )
        if users_list_count >= 1
        else ("0 users here for now.\n")
    )
    return (
        f"Location received !!!\n"
        f"Now, your are ***__{user_new_name}__***.\n"
        f"{suggest_to_connect}\n"
        "Note: Everything here is encrypted and the chat will be cleaned when you change place.\n"
        "For any question, please address to @sanixdarker"
    )


# --------------------------------------------------------------------------- #
# Clock abstraction (injected so idle-eviction is deterministic in tests)
# --------------------------------------------------------------------------- #
class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    """Wall-clock time in epoch seconds."""

    def now(self) -> float:
        return time.time()


class FakeClock:
    """Controllable clock for tests."""

    def __init__(self, t: float = 0.0) -> None:
        self._t = t

    def now(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt

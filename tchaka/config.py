"""Typed configuration and i18n strings for tchaka.

Replaces bare ``os.getenv`` string lookups with a validated, typed
:class:`Settings` object loaded by :func:`load_settings`.  Numeric settings
fall back to documented defaults when the environment value is missing, empty,
or malformed -- configuration parsing never crashes (except for a missing
``TG_TOKEN``, which is fatal by design).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_LOGGER = logging.getLogger(__name__)

# Defaults (documented in .env.example)
DEFAULT_RANGE_KM = 5.0
DEFAULT_IDLE_TTL_SECONDS = 3600
DEFAULT_SWEEP_INTERVAL_SECONDS = 300
DEFAULT_MAX_RELAY_CHARS = 500
DEFAULT_MAX_ERROR_CHARS = 3500  # stays under Telegram's 4096-char hard limit


@dataclass(frozen=True)
class Settings:
    """Immutable, validated runtime configuration."""

    tg_token: str
    developer_chat_id: int | None
    distance_threshold_km: float
    idle_ttl_seconds: int
    sweep_interval_seconds: int
    max_relay_chars: int
    max_error_chars: int


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        _LOGGER.warning("Invalid float for %s=%r; using default %s", name, raw, default)
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        _LOGGER.warning("Invalid int for %s=%r; using default %s", name, raw, default)
        return default


def _parse_developer_chat_id(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    candidate = raw.strip()
    if candidate.lstrip("-").isdigit():
        return int(candidate)
    _LOGGER.warning("Invalid DEVELOPER_CHAT_ID=%r; ignoring", raw)
    return None


def load_settings() -> Settings:
    """Load and validate settings from the environment.

    Raises :class:`SystemExit` only when ``TG_TOKEN`` is missing/empty.
    """
    token = os.getenv("TG_TOKEN")
    if not token or not token.strip():
        raise SystemExit("TG_TOKEN not found, please set it in .env")

    return Settings(
        tg_token=token,
        developer_chat_id=_parse_developer_chat_id(os.getenv("DEVELOPER_CHAT_ID")),
        distance_threshold_km=_get_float("TCHAKA_RANGE_KM", DEFAULT_RANGE_KM),
        idle_ttl_seconds=_get_int("TCHAKA_IDLE_TTL_SECONDS", DEFAULT_IDLE_TTL_SECONDS),
        sweep_interval_seconds=_get_int(
            "TCHAKA_SWEEP_INTERVAL_SECONDS", DEFAULT_SWEEP_INTERVAL_SECONDS
        ),
        max_relay_chars=_get_int("TCHAKA_MAX_RELAY_CHARS", DEFAULT_MAX_RELAY_CHARS),
        max_error_chars=_get_int("TCHAKA_MAX_ERROR_CHARS", DEFAULT_MAX_ERROR_CHARS),
    )


# Backwards-compatible module-level values (used by the error handler default
# and any code still importing these names directly).
DEVELOPER_CHAT_ID = _parse_developer_chat_id(os.getenv("DEVELOPER_CHAT_ID"))
TG_TOKEN = os.getenv("TG_TOKEN")


LANG_MESSAGES: dict[str, dict[str, str]] = {
    "fr": {
        "WELCOME_MESSAGE": """Bienvenue sur Tchaka!
Commencez par envoyer votre localisation (aucun soucis, c est anonyme et rien
ne se sauvegardes)""",
        "HELP_MESSAGE": """/start - Pour demarrer.
/help - Comment cela fonctionne.
/check - Voir combien de personnes sont autour de vous.
/stop - Pour stoper le bot et cleaner toutes vos infos.

Si vous avez toujours un problème, veuillez contacter le dév
@sanixdarker.""",
        "CHECK_RESULT": "Il y a {n} personne(s) autour de vous.",
        "CHECK_ALONE": "Personne autour de vous pour le moment.",
        "CHECK_NOT_REGISTERED": (
            "Envoyez d'abord votre localisation pour rejoindre une zone."
        ),
        "IDLE_EVICTED": (
            "Vous avez été retiré de la zone pour cause d'inactivité. "
            "Renvoyez votre localisation pour revenir."
        ),
    },
    "en": {
        "WELCOME_MESSAGE": """Welcome to Tchaka!
Start by sending your localisation and get guided (No worries, it is anonym and not stored)""",
        "HELP_MESSAGE": """/start - To get started.
/help - How it works
/check - See how many people are around you.
/stop - To Stop the bot and clean all your infos.

If you still have a
problem, please contact the developer at @sanixdarker.
""",
        "CHECK_RESULT": "There are {n} person(s) around you.",
        "CHECK_ALONE": "Nobody around you right now.",
        "CHECK_NOT_REGISTERED": "Send your location first to join an area.",
        "IDLE_EVICTED": (
            "You were removed from the area due to inactivity. "
            "Send your location again to come back."
        ),
    },
}

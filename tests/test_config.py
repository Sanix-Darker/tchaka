"""Tests for the typed configuration loader and i18n message keys.

Property coverage: P-CFG-1 (safe parse never raises except missing token),
P-CFG-2 (configured range applied -- verified indirectly via Settings value).
"""

from __future__ import annotations

import importlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

import tchaka.config as config_module
from tchaka.config import (
    DEFAULT_IDLE_TTL_SECONDS,
    DEFAULT_MAX_ERROR_CHARS,
    DEFAULT_MAX_RELAY_CHARS,
    DEFAULT_RANGE_KM,
    DEFAULT_SWEEP_INTERVAL_SECONDS,
    LANG_MESSAGES,
    load_settings,
)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "TG_TOKEN",
        "DEVELOPER_CHAT_ID",
        "TCHAKA_RANGE_KM",
        "TCHAKA_IDLE_TTL_SECONDS",
        "TCHAKA_SWEEP_INTERVAL_SECONDS",
        "TCHAKA_MAX_RELAY_CHARS",
        "TCHAKA_MAX_ERROR_CHARS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_applied_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TG_TOKEN", "tok")
    s = load_settings()
    assert s.tg_token == "tok"
    assert s.developer_chat_id is None
    assert s.distance_threshold_km == DEFAULT_RANGE_KM
    assert s.idle_ttl_seconds == DEFAULT_IDLE_TTL_SECONDS
    assert s.sweep_interval_seconds == DEFAULT_SWEEP_INTERVAL_SECONDS
    assert s.max_relay_chars == DEFAULT_MAX_RELAY_CHARS
    assert s.max_error_chars == DEFAULT_MAX_ERROR_CHARS


def test_missing_token_halts(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    with pytest.raises(SystemExit):
        load_settings()


def test_empty_token_halts(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TG_TOKEN", "   ")
    with pytest.raises(SystemExit):
        load_settings()


def test_malformed_numerics_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TG_TOKEN", "tok")
    monkeypatch.setenv("TCHAKA_RANGE_KM", "not-a-number")
    monkeypatch.setenv("TCHAKA_IDLE_TTL_SECONDS", "")
    monkeypatch.setenv("TCHAKA_MAX_RELAY_CHARS", "abc")
    s = load_settings()
    assert s.distance_threshold_km == DEFAULT_RANGE_KM
    assert s.idle_ttl_seconds == DEFAULT_IDLE_TTL_SECONDS
    assert s.max_relay_chars == DEFAULT_MAX_RELAY_CHARS


def test_valid_values_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TG_TOKEN", "tok")
    monkeypatch.setenv("DEVELOPER_CHAT_ID", "-1001234")
    monkeypatch.setenv("TCHAKA_RANGE_KM", "12.5")
    monkeypatch.setenv("TCHAKA_IDLE_TTL_SECONDS", "60")
    s = load_settings()
    assert s.developer_chat_id == -1001234
    assert s.distance_threshold_km == 12.5
    assert s.idle_ttl_seconds == 60


def test_invalid_developer_chat_id_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TG_TOKEN", "tok")
    monkeypatch.setenv("DEVELOPER_CHAT_ID", "not-an-id")
    s = load_settings()
    assert s.developer_chat_id is None


@given(
    range_raw=st.text(
        alphabet=st.characters(min_codepoint=1, max_codepoint=0xD7FF), max_size=12
    ),
    ttl_raw=st.text(
        alphabet=st.characters(min_codepoint=1, max_codepoint=0xD7FF), max_size=12
    ),
    sweep_raw=st.text(
        alphabet=st.characters(min_codepoint=1, max_codepoint=0xD7FF), max_size=12
    ),
)
def test_safe_parse_never_raises_with_token(
    range_raw: str, ttl_raw: str, sweep_raw: str
) -> None:
    # P-CFG-1: with a token present, arbitrary numeric strings never crash.
    # Null bytes (codepoint 0) and surrogates are excluded because the OS
    # forbids them in environment variables.
    import os

    os.environ["TG_TOKEN"] = "tok"
    os.environ["TCHAKA_RANGE_KM"] = range_raw
    os.environ["TCHAKA_IDLE_TTL_SECONDS"] = ttl_raw
    os.environ["TCHAKA_SWEEP_INTERVAL_SECONDS"] = sweep_raw
    try:
        s = load_settings()
        assert isinstance(s.distance_threshold_km, float)
        assert isinstance(s.idle_ttl_seconds, int)
        assert isinstance(s.sweep_interval_seconds, int)
    finally:
        for k in (
            "TCHAKA_RANGE_KM",
            "TCHAKA_IDLE_TTL_SECONDS",
            "TCHAKA_SWEEP_INTERVAL_SECONDS",
        ):
            os.environ.pop(k, None)


@pytest.mark.parametrize("lang", ["en", "fr"])
@pytest.mark.parametrize(
    "key",
    [
        "WELCOME_MESSAGE",
        "HELP_MESSAGE",
        "CHECK_RESULT",
        "CHECK_ALONE",
        "CHECK_NOT_REGISTERED",
        "IDLE_EVICTED",
    ],
)
def test_i18n_keys_present(lang: str, key: str) -> None:
    assert key in LANG_MESSAGES[lang]
    assert LANG_MESSAGES[lang][key].strip() != ""


def test_check_result_formats_count() -> None:
    for lang in ("en", "fr"):
        rendered = LANG_MESSAGES[lang]["CHECK_RESULT"].format(n=3)
        assert "3" in rendered


def test_module_importable() -> None:
    # Guard against import-time crashes.
    importlib.reload(config_module)

"""Shared pytest configuration for the tchaka test-suite.

The project historically mixed ``@pytest.mark.anyio`` and
``@pytest.mark.asyncio`` markers.  We standardize the async backend on
``asyncio`` so the whole suite runs consistently without requiring ``trio``:

- ``pytest-asyncio`` (``asyncio_mode = "auto"`` in ``pyproject.toml``) handles
  the plain ``async def`` tests and the ``@pytest.mark.asyncio`` ones.
- The ``anyio_backend`` fixture below pins ``@pytest.mark.anyio`` tests to the
  asyncio backend.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

"""Fixtures for the tests that run against a real Home Assistant.

These need `requirements-test.txt` installed. They are deliberately kept apart from
`tests/standalone/`, whose conftest stubs `homeassistant.*` into `sys.modules` at
collection time -- the two cannot share a process.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant find custom_components/woow_zha_quirks."""
    yield


@pytest.fixture(autouse=True)
def no_quirk_heal():
    """Stop quirk_heal from waiting a real minute for a ZHA gateway that isn't there.

    `_async_heal` is the one hook scheduled as a *foreground* task, so
    `hass.async_block_till_done()` waits on its bounded 6x10 s gateway retry. Every other
    hook uses `async_create_background_task`, which block-till-done ignores.
    """
    with patch(
        "custom_components.woow_zha_quirks.quirk_heal._async_heal",
        new=AsyncMock(return_value=None),
    ):
        yield

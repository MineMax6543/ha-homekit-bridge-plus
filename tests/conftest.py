"""Fixtures for HomeKit Bridge Plus tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components."""
    return


@pytest.fixture
def mock_network(mock_async_zeroconf, mock_get_source_ip) -> Generator[None]:
    """Keep the HAP driver off the network and the disk."""
    with (
        patch("custom_components.homekit_plus.bridge.HomeDriver.persist"),
        patch(
            "custom_components.homekit_plus.bridge.network.async_get_source_ip",
            AsyncMock(return_value="127.0.0.1"),
        ),
        patch(
            "custom_components.homekit_plus.bridge.zeroconf.async_get_async_instance",
            AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "custom_components.homekit_plus.bridge.HomeDriver.async_start",
            AsyncMock(),
        ),
        patch(
            "custom_components.homekit_plus.bridge.HomeDriver.async_stop",
            AsyncMock(),
        ),
    ):
        yield

"""Tests for the config and options flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.homekit_plus.const import DOMAIN


@pytest.fixture(autouse=True)
def port_free():
    with patch("custom_components.homekit_plus.config_flow._port_free", return_value=True):
        yield


@pytest.mark.usefixtures("mock_network")
async def test_full_flow(hass: HomeAssistant) -> None:
    hass.states.async_set("light.kitchen", "on", {"supported_color_modes": ["hs"]})
    hass.states.async_set("sensor.odd", "5", {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"mode": "bridge"}
    )
    assert result["step_id"] == "bridge"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Bridge", "port": 21080, "entities": ["light.kitchen", "sensor.odd"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data["port"] == 21080
    assert len(entry.data["pincode"]) == 10
    await hass.async_block_till_done()

    # options: configure the unknown sensor as a light sensor
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "configure_entity"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"entity": "sensor.odd"}
    )
    assert result["step_id"] == "entity_type"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"type": "light_sensor", "name": "Lux", "reset": False}
    )
    assert result["step_id"] == "entity_options"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"low_battery_threshold": 20}
    )
    assert result["type"] is FlowResultType.MENU

    # light: only on/off
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "configure_entity"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"entity": "light.kitchen"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"type": "lightbulb", "reset": False}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"features": [], "low_battery_threshold": 20}
    )

    # combined accessory
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "groups"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"group": "__new__"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Kitchen", "entities": ["light.kitchen", "sensor.odd"]}
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "save"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    opts = entry.options
    assert opts["entity_config"]["sensor.odd"]["type"] == "light_sensor"
    assert opts["entity_config"]["sensor.odd"]["name"] == "Lux"
    assert opts["entity_config"]["light.kitchen"]["features"] == []
    assert opts["groups"][0]["entities"] == ["light.kitchen", "sensor.odd"]

    bridge = entry.runtime_data
    acc = bridge.handlers_by_entity["sensor.odd"][0].acc
    assert acc is bridge.handlers_by_entity["light.kitchen"][0].acc
    assert {s.display_name for s in acc.services} >= {"Lightbulb", "LightSensor"}


@pytest.mark.usefixtures("mock_network")
async def test_port_conflict(hass: HomeAssistant) -> None:
    with patch("custom_components.homekit_plus.config_flow._port_free", return_value=False):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"mode": "bridge"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Bridge", "port": 21080}
        )
    assert result["errors"] == {"port": "port_in_use"}

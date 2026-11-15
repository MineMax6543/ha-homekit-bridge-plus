"""Removing entities from a bridge through the options flow."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.homekit_plus.const import DOMAIN


async def _entry(hass: HomeAssistant, options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Test", "port": 21099, "pincode": "123-45-678", "mode": "bridge"},
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _remove_via_flow(hass, entry, keep):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_entities"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"entities": keep} if keep else {}
    )
    return result


@pytest.mark.usefixtures("mock_network")
async def test_remove_some(hass: HomeAssistant) -> None:
    for e in ("switch.a", "switch.b", "switch.c"):
        hass.states.async_set(e, "on")
    entry = await _entry(hass, {"entities": ["switch.a", "switch.b", "switch.c"]})
    result = await _remove_via_flow(hass, entry, ["switch.a"])
    # applied on submit, no extra "save" step that could be skipped
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert sorted(entry.runtime_data.handlers_by_entity) == ["switch.a"]


@pytest.mark.usefixtures("mock_network")
async def test_remove_all(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.a", "on")
    entry = await _entry(hass, {"entities": ["switch.a"]})
    result = await _remove_via_flow(hass, entry, [])
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert not entry.runtime_data.handlers_by_entity


@pytest.mark.usefixtures("mock_network")
async def test_form_explains_indirectly_exposed(hass: HomeAssistant) -> None:
    """Entities exposed via a domain filter can't be removed from the list."""
    hass.states.async_set("switch.a", "on")
    hass.states.async_set("light.l", "on", {"supported_color_modes": ["onoff"]})
    entry = await _entry(hass, {"entities": ["switch.a"], "include_domains": ["light"]})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_entities"}
    )
    assert "`light.l`" in result["description_placeholders"]["indirect"]
    assert "switch.a" not in result["description_placeholders"]["indirect"]

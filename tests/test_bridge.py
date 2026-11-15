"""Tests for accessory creation, feature selection and state sync."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, label_registry as lr

from custom_components.homekit_plus.const import DOMAIN

LIGHT_ATTRS = {
    "friendly_name": "Ceiling",
    "supported_color_modes": ["color_temp", "hs"],
    "brightness": 128,
    "color_temp_kelvin": 3000,
    "min_color_temp_kelvin": 2000,
    "max_color_temp_kelvin": 6500,
    "hs_color": [30, 50],
}


def _service(acc, name):
    return next(s for s in acc.services if s.display_name == name)


def _chars(serv) -> set[str]:
    return {c.display_name for c in serv.characteristics}


async def _setup(hass: HomeAssistant, options: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Test Bridge", "port": 21099, "pincode": "123-45-678"},
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _acc_by_entity(entry, entity_id):
    bridge = entry.runtime_data
    handler = bridge.handlers_by_entity[entity_id][0]
    return handler.acc


@pytest.mark.usefixtures("mock_network")
async def test_light_feature_selection(hass: HomeAssistant) -> None:
    hass.states.async_set("light.ceiling", "on", LIGHT_ATTRS)
    hass.states.async_set("light.full", "on", LIGHT_ATTRS)
    entry = await _setup(
        hass,
        {
            "entities": ["light.ceiling", "light.full"],
            "entity_config": {
                "light.ceiling": {"name": "Big Lamp", "features": ["brightness"]},
            },
        },
    )
    acc = _acc_by_entity(entry, "light.ceiling")
    serv = _service(acc, "Lightbulb")
    assert {"On", "Brightness"} <= _chars(serv)
    assert "ColorTemperature" not in _chars(serv)
    assert "Hue" not in _chars(serv)
    assert acc.display_name == "Big Lamp"
    assert serv.get_characteristic("Brightness").value == 50

    full = _service(_acc_by_entity(entry, "light.full"), "Lightbulb")
    assert {"On", "Brightness", "ColorTemperature", "Hue", "Saturation"} <= _chars(full)
    assert full.get_characteristic("ColorTemperature").value == 333

    # HomeKit -> HA
    calls = async_mock_service(hass, "light", "turn_on")
    serv.setter_callback({"On": True, "Brightness": 80})
    await hass.async_block_till_done()
    assert calls[-1].data == {"entity_id": "light.ceiling", "brightness_pct": 80}

    # HA -> HomeKit
    hass.states.async_set("light.ceiling", "off", LIGHT_ATTRS)
    await hass.async_block_till_done()
    assert serv.get_characteristic("On").value is False


@pytest.mark.usefixtures("mock_network")
async def test_switch_types(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.pump", "on", {"friendly_name": "Pump"})
    hass.states.async_set("input_boolean.guest", "off", {"friendly_name": "Guest"})
    hass.states.async_set("switch.lamp", "off", {"friendly_name": "Lamp"})
    entry = await _setup(
        hass,
        {
            "entities": ["switch.pump", "input_boolean.guest", "switch.lamp"],
            "entity_config": {
                "switch.pump": {"type": "sprinkler"},
                "input_boolean.guest": {"type": "motion", "invert": True},
                "switch.lamp": {"type": "lightbulb"},
            },
        },
    )
    pump = _service(_acc_by_entity(entry, "switch.pump"), "Valve")
    assert pump.get_characteristic("ValveType").value == 1
    assert pump.get_characteristic("Active").value == 1

    motion = _service(_acc_by_entity(entry, "input_boolean.guest"), "MotionSensor")
    assert motion.get_characteristic("MotionDetected").value is True  # inverted "off"

    lamp = _service(_acc_by_entity(entry, "switch.lamp"), "Lightbulb")
    calls = async_mock_service(hass, "switch", "turn_on")
    lamp.setter_callback({"On": True})
    await hass.async_block_till_done()
    assert calls[-1].data == {"entity_id": "switch.lamp"}


@pytest.mark.usefixtures("mock_network")
async def test_thermostat_modes_and_linked_battery(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "climate.living",
        "heat",
        {
            "friendly_name": "Living",
            "hvac_modes": ["off", "heat", "cool", "heat_cool"],
            "current_temperature": 20.5,
            "temperature": 22,
            "min_temp": 7,
            "max_temp": 30,
            "supported_features": 1,
            "hvac_action": "heating",
        },
    )
    hass.states.async_set(
        "sensor.trv_battery", "15", {"device_class": "battery", "unit_of_measurement": "%"}
    )
    entry = await _setup(
        hass,
        {
            "entities": ["climate.living"],
            "entity_config": {
                "climate.living": {
                    "hvac_modes": ["off", "heat"],
                    "linked_battery_sensor": "sensor.trv_battery",
                }
            },
        },
    )
    acc = _acc_by_entity(entry, "climate.living")
    thermo = _service(acc, "Thermostat")
    target = thermo.get_characteristic("TargetHeatingCoolingState")
    assert set(target.properties["ValidValues"].values()) == {0, 1}
    assert target.value == 1
    assert thermo.get_characteristic("CurrentHeatingCoolingState").value == 1
    assert thermo.get_characteristic("TargetTemperature").value == 22
    battery = _service(acc, "BatteryService")
    assert battery.get_characteristic("BatteryLevel").value == 15
    assert battery.get_characteristic("StatusLowBattery").value == 1

    calls = async_mock_service(hass, "climate", "set_hvac_mode")
    thermo.setter_callback({"TargetHeatingCoolingState": 0})
    await hass.async_block_till_done()
    assert calls[-1].data["hvac_mode"] == "off"


@pytest.mark.usefixtures("mock_network")
async def test_cover_open_close_only(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "cover.blind",
        "open",
        {"friendly_name": "Blind", "current_position": 40, "supported_features": 15 | 128},
    )
    entry = await _setup(
        hass,
        {"entities": ["cover.blind"], "entity_config": {"cover.blind": {"features": []}}},
    )
    serv = _service(_acc_by_entity(entry, "cover.blind"), "WindowCovering")
    assert "TargetHorizontalTiltAngle" not in _chars(serv)
    assert serv.get_characteristic("CurrentPosition").value == 100
    calls = async_mock_service(hass, "cover", "close_cover")
    serv.setter_callback({"TargetPosition": 0})
    await hass.async_block_till_done()
    assert len(calls) == 1


@pytest.mark.usefixtures("mock_network")
async def test_combined_accessory_and_label_include(hass: HomeAssistant) -> None:
    ent_reg = er.async_get(hass)
    label = lr.async_get(hass).async_create("HomeKit")
    temp = ent_reg.async_get_or_create("sensor", "test", "t1", suggested_object_id="temp")
    hum = ent_reg.async_get_or_create("sensor", "test", "h1", suggested_object_id="hum")
    tagged = ent_reg.async_get_or_create("switch", "test", "s1", suggested_object_id="tagged")
    ent_reg.async_update_entity(tagged.entity_id, labels={label.label_id})
    hass.states.async_set(temp.entity_id, "21.5", {"device_class": "temperature", "unit_of_measurement": "°C"})
    hass.states.async_set(hum.entity_id, "55", {"device_class": "humidity", "unit_of_measurement": "%"})
    hass.states.async_set(tagged.entity_id, "on")
    hass.states.async_set("sensor.mystery", "3", {})

    entry = await _setup(
        hass,
        {
            "entities": ["sensor.mystery"],
            "include_labels": [label.label_id],
            "groups": [
                {"id": "g1", "name": "Climate Sensor", "entities": [temp.entity_id, hum.entity_id]}
            ],
        },
    )
    bridge = entry.runtime_data
    assert len(bridge.bridge.accessories) == 2  # group + tagged switch
    acc = _acc_by_entity(entry, temp.entity_id)
    assert acc is _acc_by_entity(entry, hum.entity_id)
    assert acc.display_name == "Climate Sensor"
    assert _service(acc, "TemperatureSensor").get_characteristic("CurrentTemperature").value == 21.5
    assert _service(acc, "HumiditySensor").get_characteristic("CurrentRelativeHumidity").value == 55
    assert "sensor.mystery" in bridge.skipped
    assert tagged.entity_id in bridge.handlers_by_entity


@pytest.mark.usefixtures("mock_network")
async def test_security_system_and_lock(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "alarm_control_panel.home", "armed_away", {"supported_features": 1 | 2 | 4}
    )
    hass.states.async_set("lock.front", "locked", {})
    entry = await _setup(
        hass,
        {
            "entities": ["alarm_control_panel.home", "lock.front"],
            "entity_config": {
                "alarm_control_panel.home": {"alarm_modes": ["away"], "code": "1234"},
            },
        },
    )
    alarm = _service(_acc_by_entity(entry, "alarm_control_panel.home"), "SecuritySystem")
    target = alarm.get_characteristic("SecuritySystemTargetState")
    assert set(target.properties["ValidValues"].values()) == {1, 3}
    assert target.value == 1
    calls = async_mock_service(hass, "alarm_control_panel", "alarm_disarm")
    alarm.setter_callback({"SecuritySystemTargetState": 3})
    await hass.async_block_till_done()
    assert calls[-1].data["code"] == "1234"

    lock = _service(_acc_by_entity(entry, "lock.front"), "LockMechanism")
    assert lock.get_characteristic("LockCurrentState").value == 1


@pytest.mark.usefixtures("mock_network")
async def test_stable_aids_across_reload(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.a", "on")
    hass.states.async_set("switch.b", "on")
    entry = await _setup(hass, {"entities": ["switch.a", "switch.b"]})
    aid_b = _acc_by_entity(entry, "switch.b").aid

    hass.config_entries.async_update_entry(entry, options={"entities": ["switch.b"]})
    await hass.async_block_till_done()
    assert _acc_by_entity(entry, "switch.b").aid == aid_b


@pytest.mark.usefixtures("mock_network")
async def test_hap_roundtrip(hass: HomeAssistant) -> None:
    """Serialize everything like iOS does and write through the HAP driver."""
    hass.states.async_set("light.ceiling", "on", LIGHT_ATTRS)
    hass.states.async_set("fan.f", "on", {"supported_features": 1 | 2, "percentage": 50})
    hass.states.async_set("binary_sensor.door", "on", {"device_class": "door"})
    hass.states.async_set("sensor.pm", "20", {"device_class": "pm25"})
    hass.states.async_set("sensor.co2", "1200", {"device_class": "carbon_dioxide"})
    hass.states.async_set("cover.garage", "closed", {"device_class": "garage"})
    hass.states.async_set("script.go", "off", {})
    entry = await _setup(
        hass,
        {"entities": ["light.ceiling", "fan.f", "binary_sensor.door", "sensor.pm",
                      "sensor.co2", "cover.garage", "script.go"]},
    )
    driver = entry.runtime_data.driver
    hap = driver.get_accessories()
    assert len(hap["accessories"]) == 8  # bridge + 7

    script_acc = _acc_by_entity(entry, "script.go")
    on_char = _service(script_acc, "Switch").get_characteristic("On")
    calls = async_mock_service(hass, "script", "turn_on")
    driver.set_characteristics(
        {"characteristics": [{"aid": script_acc.aid, "iid": script_acc.iid_manager.get_iid(on_char), "value": True}]},
        ("127.0.0.1", 1234),
    )
    await hass.async_block_till_done()
    assert calls[-1].data == {"entity_id": "script.go"}
    assert on_char.value is True  # resets after a second

    assert _service(_acc_by_entity(entry, "binary_sensor.door"), "ContactSensor").get_characteristic("ContactSensorState").value == 1
    assert _service(_acc_by_entity(entry, "sensor.pm"), "AirQualitySensor").get_characteristic("AirQuality").value == 2
    assert _service(_acc_by_entity(entry, "sensor.co2"), "CarbonDioxideSensor").get_characteristic("CarbonDioxideDetected").value == 1
    assert _service(_acc_by_entity(entry, "cover.garage"), "GarageDoorOpener").get_characteristic("CurrentDoorState").value == 1


@pytest.mark.parametrize(("on_value", "service"), [(1, "turn_on"), (0, "turn_off"), (True, "turn_on"), (False, "turn_off")])
@pytest.mark.usefixtures("mock_network")
async def test_light_tap_with_numeric_on(hass: HomeAssistant, on_value, service) -> None:
    """iOS may send On as 1/0 when the tile icon is tapped (WLED report)."""
    attrs = {"friendly_name": "WLED", "supported_color_modes": ["rgb"], "brightness": 200, "hs_color": [20, 80]}
    hass.states.async_set("light.wled", "off" if on_value else "on", attrs)
    entry = await _setup(hass, {"entities": ["light.wled"]})
    acc = _acc_by_entity(entry, "light.wled")
    on_char = _service(acc, "Lightbulb").get_characteristic("On")
    calls = async_mock_service(hass, "light", service)
    entry.runtime_data.driver.set_characteristics(
        {"characteristics": [{"aid": acc.aid, "iid": acc.iid_manager.get_iid(on_char), "value": on_value}]},
        ("127.0.0.1", 1234),
    )
    await hass.async_block_till_done()
    assert len(calls) == 1

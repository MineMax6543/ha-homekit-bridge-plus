"""Tests for TV/accessory mode, humidifier, water heater and camera."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_mock_service,
)

from homeassistant import config_entries
import homeassistant.components.camera  # noqa: F401  (patched below)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.homekit_plus.accessory import (
    HACameraAccessory,
    build_ffmpeg_args,
)
from custom_components.homekit_plus.const import DOMAIN

TV_ATTRS = {
    "friendly_name": "Living TV",
    "device_class": "tv",
    "supported_features": 128 | 256 | 2048 | 1024 | 8 | 16384 | 1,
    "source_list": ["HDMI 1", "HDMI 2", "Netflix", "YouTube"],
    "source": "Netflix",
    "is_volume_muted": False,
}


def _service(acc, name):
    return next(s for s in acc.services if s.display_name == name)


def _services(acc, name):
    return [s for s in acc.services if s.display_name == name]


async def _setup(hass: HomeAssistant, options: dict[str, Any], **data: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Test", "port": 21099, "pincode": "123-45-678", **data},
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _acc(entry, entity_id):
    return entry.runtime_data.handlers_by_entity[entity_id][0].acc


@pytest.mark.usefixtures("mock_network")
async def test_tv_accessory_mode(hass: HomeAssistant) -> None:
    hass.states.async_set("media_player.tv", "on", TV_ATTRS)
    entry = await _setup(
        hass,
        {
            "entities": ["media_player.tv"],
            "entity_config": {"media_player.tv": {"sources": ["HDMI 1", "Netflix"]}},
        },
        mode="accessory",
    )
    bridge = entry.runtime_data
    acc = bridge.root
    assert bridge.bridge is None
    assert acc.aid == 1
    assert acc.category == 31
    assert acc.display_name == "Test"
    tv = _service(acc, "Television")
    inputs = _services(acc, "InputSource")
    assert [i.get_characteristic("ConfiguredName").value for i in inputs] == ["HDMI 1", "Netflix"]
    assert tv.get_characteristic("ActiveIdentifier").value == 1  # Netflix
    assert tv.get_characteristic("Active").value == 1
    assert _service(acc, "TelevisionSpeaker")

    # Serializes like iOS requests it (standalone accessory)
    assert len(bridge.driver.get_accessories()["accessories"]) == 1

    select = async_mock_service(hass, "media_player", "select_source")
    play = async_mock_service(hass, "media_player", "media_play_pause")
    events = async_capture_events(hass, "homekit_plus_tv_remote_key_pressed")
    tv.setter_callback({"ActiveIdentifier": 0})
    tv.setter_callback({"RemoteKey": 11})
    tv.setter_callback({"RemoteKey": 4})
    await hass.async_block_till_done()
    assert select[-1].data["source"] == "HDMI 1"
    assert len(play) == 1
    assert events[-1].data == {"entity_id": "media_player.tv", "key_name": "arrow_up"}

    mute = async_mock_service(hass, "media_player", "volume_mute")
    _service(acc, "TelevisionSpeaker").setter_callback({"Mute": True})
    await hass.async_block_till_done()
    assert mute[-1].data["is_volume_muted"] is True


@pytest.mark.usefixtures("mock_network")
async def test_tv_in_bridge_mode_is_switch(hass: HomeAssistant) -> None:
    hass.states.async_set("media_player.tv", "on", TV_ATTRS)
    entry = await _setup(
        hass,
        {"entities": ["media_player.tv"], "entity_config": {"media_player.tv": {"type": "television"}}},
    )
    assert _service(_acc(entry, "media_player.tv"), "Switch")


@pytest.mark.usefixtures("mock_network")
async def test_dehumidifier_with_linked_humidity(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "humidifier.basement",
        "on",
        {"device_class": "dehumidifier", "humidity": 50, "min_humidity": 30,
         "max_humidity": 80, "action": "drying"},
    )
    hass.states.async_set("sensor.basement_h", "64", {"device_class": "humidity"})
    entry = await _setup(
        hass,
        {
            "entities": ["humidifier.basement"],
            "entity_config": {"humidifier.basement": {"linked_humidity_sensor": "sensor.basement_h"}},
        },
    )
    acc = _acc(entry, "humidifier.basement")
    assert acc.category == 23
    serv = _service(acc, "HumidifierDehumidifier")
    assert serv.get_characteristic("CurrentRelativeHumidity").value == 64
    assert serv.get_characteristic("CurrentHumidifierDehumidifierState").value == 3
    assert serv.get_characteristic("TargetHumidifierDehumidifierState").value == 2
    assert serv.get_characteristic("RelativeHumidityDehumidifierThreshold").value == 50
    assert not _services(acc, "HumiditySensor")  # fed into the char, no extra tile

    hass.states.async_set("sensor.basement_h", "58", {"device_class": "humidity"})
    await hass.async_block_till_done()
    assert serv.get_characteristic("CurrentRelativeHumidity").value == 58

    calls = async_mock_service(hass, "humidifier", "set_humidity")
    serv.setter_callback({"RelativeHumidityDehumidifierThreshold": 45})
    await hass.async_block_till_done()
    assert calls[-1].data["humidity"] == 45


@pytest.mark.usefixtures("mock_network")
async def test_water_heater(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "water_heater.boiler",
        "eco",
        {"operation_list": ["eco", "performance", "off"], "temperature": 55,
         "current_temperature": 48, "min_temp": 40, "max_temp": 65},
    )
    entry = await _setup(hass, {"entities": ["water_heater.boiler"]})
    serv = _service(_acc(entry, "water_heater.boiler"), "Thermostat")
    assert serv.get_characteristic("TargetTemperature").value == 55
    assert serv.get_characteristic("CurrentTemperature").value == 48
    assert serv.get_characteristic("TargetHeatingCoolingState").value == 1

    calls = async_mock_service(hass, "water_heater", "set_operation_mode")
    serv.setter_callback({"TargetHeatingCoolingState": 0})
    await hass.async_block_till_done()
    assert calls[-1].data["operation_mode"] == "off"


@pytest.mark.usefixtures("mock_network")
async def test_camera_with_doorbell_and_motion(hass: HomeAssistant) -> None:
    hass.states.async_set("camera.front", "idle", {"friendly_name": "Front"})
    hass.states.async_set("binary_sensor.front_motion", "off", {"device_class": "motion"})
    hass.states.async_set("binary_sensor.front_bell", "off", {})
    entry = await _setup(
        hass,
        {
            "entities": ["camera.front"],
            "entity_config": {
                "camera.front": {
                    "stream_source": "rtsp://cam/stream",
                    "video_codec": "copy",
                    "support_audio": True,
                    "max_height": 720,
                    "linked_motion_sensor": "binary_sensor.front_motion",
                    "linked_doorbell_sensor": "binary_sensor.front_bell",
                }
            },
        },
    )
    acc = _acc(entry, "camera.front")
    assert isinstance(acc, HACameraAccessory)
    assert acc.category == 18  # video doorbell
    names = {s.display_name for s in acc.services}
    assert {"CameraRTPStreamManagement", "Doorbell", "MotionSensor", "Microphone"} <= names
    assert len(entry.runtime_data.driver.get_accessories()["accessories"]) == 2

    motion = _service(acc, "MotionSensor").get_characteristic("MotionDetected")
    hass.states.async_set("binary_sensor.front_motion", "on", {"device_class": "motion"})
    await hass.async_block_till_done()
    assert motion.value is True

    bell = entry.runtime_data.handlers_by_entity["binary_sensor.front_bell"][0]
    assert bell.char_event is _service(acc, "Doorbell").get_characteristic(
        "ProgrammableSwitchEvent"
    )
    with patch.object(bell, "char_event") as ring:
        hass.states.async_set("binary_sensor.front_bell", "on", {})
        await hass.async_block_till_done()
        hass.states.async_set("binary_sensor.front_bell", "on", {"x": 1})  # no edge
        await hass.async_block_till_done()
    ring.set_value.assert_called_once_with(0)

    # snapshot through HA's camera component
    with patch(
        "homeassistant.components.camera.async_get_image",
        AsyncMock(return_value=MagicMock(content=b"jpeg")),
    ) as get_image:
        assert await acc.async_get_snapshot({"image-width": 640, "image-height": 360}) == b"jpeg"
    assert get_image.call_args.kwargs == {"width": 640, "height": 360}

    # streaming starts ffmpeg with an argument list
    process = MagicMock(returncode=None)
    process.stderr.readline = AsyncMock(return_value=b"")
    process.wait = AsyncMock(return_value=0)
    with (
        patch(
            "custom_components.homekit_plus.accessory.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ) as spawn,
        patch(
            "homeassistant.components.ffmpeg.get_ffmpeg_manager",
            return_value=MagicMock(binary="ffmpeg"),
        ),
    ):
        session: dict[str, Any] = {"id": "x"}
        assert await acc.start_stream(session, _stream_config())
    args = spawn.call_args.args
    assert args[:1] == ("ffmpeg",)
    assert "rtsp://cam/stream" in args
    assert "libopus" in args
    await acc.stop_stream(session)
    process.terminate.assert_called_once()


def _stream_config() -> dict[str, Any]:
    return {
        "address": "192.168.1.50",
        "v_port": 50000,
        "v_srtp_key": "a2V5a2V5a2V5a2V5a2V5a2V5a2V5a2V5a2V5",
        "v_max_bitrate": 299,
        "v_ssrc": 12345,
        "v_profile_id": b"\x02",
        "fps": 30,
        "width": 1280,
        "height": 720,
        "a_port": 50002,
        "a_srtp_key": "a2V5a2V5a2V5a2V5a2V5a2V5a2V5a2V5a2V5",
        "a_ssrc": 54321,
        "a_sample_rate": 24,
        "a_max_bitrate": 24,
    }


def test_ffmpeg_args_transcode() -> None:
    args = build_ffmpeg_args(
        "ffmpeg", "rtsp://cam/s", {"video_codec": "libx264"}, _stream_config()
    )
    assert args[args.index("-rtsp_transport") + 1] == "tcp"
    assert args[args.index("-profile:v") + 1] == "high"
    assert args[args.index("-vf") + 1] == "scale=-2:720"
    assert "-c:a" not in args  # audio off by default
    assert args[-1] == (
        "srtp://192.168.1.50:50000?rtcpport=50000&localrtcpport=50000&pkt_size=1316"
    )


@pytest.mark.usefixtures("mock_network")
async def test_accessory_mode_flow(hass: HomeAssistant) -> None:
    hass.states.async_set("media_player.tv", "off", TV_ATTRS)
    with patch("custom_components.homekit_plus.config_flow._port_free", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"mode": "accessory"}
        )
        assert result["step_id"] == "accessory"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"entities": "media_player.tv", "port": 21090}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.title == "Living TV"
    assert entry.data["mode"] == "accessory"
    await hass.async_block_till_done()
    assert entry.runtime_data.root.category == 31

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "groups" not in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "configure_entity"}
    )
    assert result["step_id"] == "entity_type"  # the single entity is picked directly
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"type": "television", "reset": False}
    )
    assert result["step_id"] == "entity_options"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"features": ["power", "inputs"], "sources": ["HDMI 2"], "low_battery_threshold": 20},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "save"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    acc = entry.runtime_data.root
    assert len(_services(acc, "InputSource")) == 1
    assert not _services(acc, "TelevisionSpeaker")

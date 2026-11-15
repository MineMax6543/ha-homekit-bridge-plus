"""Television / receiver handler (accessory mode)."""

from __future__ import annotations

from typing import Any

from pyhap.const import CATEGORY_TELEVISION

from homeassistant.core import State

from ..const import (
    CONF_SOURCES,
    EVENT_REMOTE_KEY,
    FEATURE_INPUTS,
    FEATURE_MUTE,
    FEATURE_PLAY_PAUSE,
    FEATURE_POWER,
    FEATURE_REMOTE_EVENTS,
    FEATURE_VOLUME,
    TYPE_RECEIVER,
)
from ..util import cleanup_name, is_on, resolve_features
from .base import Handler

CATEGORY_RECEIVER = 34
MAX_SOURCES = 90

# MediaPlayerEntityFeature bit flags
_PAUSE = 1
_VOLUME_SET = 4
_VOLUME_MUTE = 8
_PREVIOUS_TRACK = 16
_NEXT_TRACK = 32
_TURN_ON = 128
_TURN_OFF = 256
_VOLUME_STEP = 1024
_SELECT_SOURCE = 2048
_PLAY = 16384

REMOTE_KEYS = {
    0: "rewind",
    1: "fast_forward",
    2: "next_track",
    3: "previous_track",
    4: "arrow_up",
    5: "arrow_down",
    6: "arrow_left",
    7: "arrow_right",
    8: "select",
    9: "back",
    10: "exit",
    11: "play_pause",
    15: "information",
}


def supported_tv_features(state: State) -> set[str]:
    """Features the media player actually supports."""
    flags = int(state.attributes.get("supported_features") or 0)
    result = {FEATURE_REMOTE_EVENTS}
    if flags & (_TURN_ON | _TURN_OFF):
        result.add(FEATURE_POWER)
    if flags & _SELECT_SOURCE and state.attributes.get("source_list"):
        result.add(FEATURE_INPUTS)
    if flags & (_VOLUME_STEP | _VOLUME_SET):
        result.add(FEATURE_VOLUME)
    if flags & _VOLUME_MUTE:
        result.add(FEATURE_MUTE)
    if flags & (_PLAY | _PAUSE):
        result.add(FEATURE_PLAY_PAUSE)
    return result


def _source_type(name: str) -> int:
    lowered = name.lower()
    if "hdmi" in lowered:
        return 3
    if "airplay" in lowered:
        return 8
    if "usb" in lowered:
        return 9
    if lowered in ("tv", "live tv", "tuner", "antenna", "cable"):
        return 2
    return 10  # application


class TelevisionHandler(Handler):
    """HomeKit Television with selectable inputs and remote features."""

    category = CATEGORY_TELEVISION

    def setup(self, state: State) -> None:
        if self.acc_type == TYPE_RECEIVER:
            self.category = CATEGORY_RECEIVER
        attrs = state.attributes
        self.features = resolve_features(self.acc_type, self.cfg) & supported_tv_features(state)

        all_sources = list(attrs.get("source_list") or [])
        chosen = self.cfg.get(CONF_SOURCES)
        self.sources: list[str] = (
            [s for s in all_sources if s in chosen] if chosen else all_sources
        )[:MAX_SOURCES]
        if FEATURE_INPUTS not in self.features:
            self.sources = []

        chars = ["Active", "ActiveIdentifier", "SleepDiscoveryMode", "RemoteKey"]
        tv = self.add_service("Television", chars)
        self.char_active = tv.configure_char("Active", value=0)
        self.char_input = tv.configure_char("ActiveIdentifier", value=0)
        tv.configure_char("SleepDiscoveryMode", value=1)
        tv.setter_callback = self.on_setter(self._set_tv)
        self.acc.set_primary_service(tv)

        for index, source in enumerate(self.sources):
            serv = self.acc.add_preload_service(
                "InputSource", ["Identifier", "Name", "ConfiguredName"]
            )
            label = cleanup_name(source, f"Input {index + 1}")
            serv.configure_char("Identifier", value=index)
            serv.configure_char("Name", value=label)
            serv.configure_char("ConfiguredName", value=label)
            serv.configure_char("InputSourceType", value=_source_type(source))
            serv.configure_char("IsConfigured", value=1)
            serv.configure_char("CurrentVisibilityState", value=0)
            tv.add_linked_service(serv)

        self.char_mute = None
        if self.features & {FEATURE_VOLUME, FEATURE_MUTE}:
            speaker = self.acc.add_preload_service(
                "TelevisionSpeaker", ["Active", "VolumeControlType", "VolumeSelector", "Name"]
            )
            speaker.configure_char("Name", value=f"{self.name} Speaker")
            speaker.configure_char("Active", value=1)
            speaker.configure_char(
                "VolumeControlType", value=1 if FEATURE_VOLUME in self.features else 0
            )
            self.char_mute = speaker.configure_char("Mute", value=False)
            speaker.setter_callback = self.on_setter(self._set_speaker)
            tv.add_linked_service(speaker)

    # ---- HomeKit -> HA ----------------------------------------------------
    def _set_tv(self, values: dict[str, Any]) -> None:
        if "Active" in values and FEATURE_POWER in self.features:
            self.call_service(
                "media_player", "turn_on" if values["Active"] == 1 else "turn_off"
            )
        if "ActiveIdentifier" in values:
            index = values["ActiveIdentifier"]
            if 0 <= index < len(self.sources):
                self.call_service(
                    "media_player", "select_source", {"source": self.sources[index]}
                )
        if "RemoteKey" in values:
            self._remote_key(values["RemoteKey"])

    def _remote_key(self, key: int) -> None:
        name = REMOTE_KEYS.get(key)
        if name is None:
            return
        if name == "play_pause" and FEATURE_PLAY_PAUSE in self.features:
            self.call_service("media_player", "media_play_pause")
            return
        if name in ("next_track", "previous_track") and FEATURE_PLAY_PAUSE in self.features:
            self.call_service("media_player", f"media_{name}")
            return
        if FEATURE_REMOTE_EVENTS in self.features:
            self.fire_event(EVENT_REMOTE_KEY, {"key_name": name})

    def _set_speaker(self, values: dict[str, Any]) -> None:
        if "VolumeSelector" in values and FEATURE_VOLUME in self.features:
            self.call_service(
                "media_player",
                "volume_down" if values["VolumeSelector"] == 1 else "volume_up",
            )
        if "Mute" in values and FEATURE_MUTE in self.features:
            self.call_service(
                "media_player", "volume_mute", {"is_volume_muted": bool(values["Mute"])}
            )

    # ---- HA -> HomeKit ----------------------------------------------------
    def async_update(self, state: State) -> None:
        self.set_char(self.char_active, 1 if is_on(state) else 0)
        source = state.attributes.get("source")
        if source in self.sources:
            self.set_char(self.char_input, self.sources.index(source))
        if self.char_mute is not None:
            self.set_char(self.char_mute, bool(state.attributes.get("is_volume_muted")))

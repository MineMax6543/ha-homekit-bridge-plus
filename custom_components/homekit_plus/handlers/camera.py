"""Camera, doorbell and characteristic-feed handlers."""

from __future__ import annotations

from typing import Any

from pyhap.const import CATEGORY_CAMERA

from homeassistant.core import State

from ..util import clamp, to_float
from .base import Handler


class CameraHandler(Handler):
    """The camera services live on the HACameraAccessory itself.

    This handler only exists so the camera entity is tracked like any other
    (availability, info service).
    """

    category = CATEGORY_CAMERA

    def setup(self, state: State) -> None:
        return

    def async_update(self, state: State) -> None:
        return


class DoorbellHandler(Handler):
    """Rings the HomeKit doorbell when a binary sensor turns on or an event fires."""

    def setup(self, state: State) -> None:
        doorbell = self.add_service("Doorbell", ["ProgrammableSwitchEvent"])
        self.char_event = doorbell.get_characteristic("ProgrammableSwitchEvent")
        # iOS expects these next to a doorbell to show notifications/controls
        switch = self.acc.add_preload_service(
            "StatelessProgrammableSwitch", ["ProgrammableSwitchEvent", "Name"]
        )
        switch.configure_char("Name", value=self.name)
        self.char_switch_event = switch.get_characteristic("ProgrammableSwitchEvent")
        speaker = self.acc.add_preload_service("Speaker", ["Mute"])
        speaker.configure_char("Mute", value=False)
        self._last: str | None = state.state

    def async_update(self, state: State) -> None:
        previous, self._last = self._last, state.state
        if previous == state.state:
            return
        if state.domain == "event":
            ring = state.state not in ("unknown", "unavailable")
        else:
            ring = state.state == "on"
        if ring:
            self.char_event.set_value(0)  # single press
            self.char_switch_event.set_value(0)


class CharFeedHandler(Handler):
    """Feeds a numeric entity into an existing characteristic (no own service)."""

    def __init__(self, *args: Any, char: Any, **kwargs: Any) -> None:
        self.char = char
        super().__init__(*args, **kwargs)

    def setup(self, state: State) -> None:
        return

    def async_update(self, state: State) -> None:
        value = to_float(state.state)
        if value is not None:
            props = self.char.properties
            self.set_char(
                self.char,
                clamp(value, props.get("minValue", 0), props.get("maxValue", 100)),
            )

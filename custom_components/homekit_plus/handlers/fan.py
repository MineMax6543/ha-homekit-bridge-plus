"""Fan handler with selectable speed / oscillation / direction."""

from __future__ import annotations

from typing import Any

from pyhap.const import CATEGORY_FAN

from homeassistant.core import State

from ..const import FEATURE_DIRECTION, FEATURE_OSCILLATE, FEATURE_SPEED
from ..util import is_on, resolve_features, to_float
from .base import Handler

# FanEntityFeature bit flags
_SET_SPEED = 1
_OSCILLATE = 2
_DIRECTION = 4


def _supported(state: State) -> set[str]:
    if state.domain != "fan":
        return set()
    flags = int(state.attributes.get("supported_features") or 0)
    result = set()
    if flags & _SET_SPEED:
        result.add(FEATURE_SPEED)
    if flags & _OSCILLATE:
        result.add(FEATURE_OSCILLATE)
    if flags & _DIRECTION:
        result.add(FEATURE_DIRECTION)
    return result


class FanHandler(Handler):
    """HomeKit Fanv2."""

    category = CATEGORY_FAN

    def setup(self, state: State) -> None:
        self.features = resolve_features(self.acc_type, self.cfg) & _supported(state)
        chars = ["Active"]
        if FEATURE_SPEED in self.features:
            chars.append("RotationSpeed")
        if FEATURE_OSCILLATE in self.features:
            chars.append("SwingMode")
        if FEATURE_DIRECTION in self.features:
            chars.append("RotationDirection")
        serv = self.add_service("Fanv2", chars)
        self.char_active = serv.configure_char("Active", value=0)
        self.char_speed = self.char_swing = self.char_direction = None
        if FEATURE_SPEED in self.features:
            step = to_float(state.attributes.get("percentage_step")) or 1
            self.char_speed = serv.configure_char(
                "RotationSpeed", properties={"minStep": step}, value=100
            )
        if FEATURE_OSCILLATE in self.features:
            self.char_swing = serv.configure_char("SwingMode", value=0)
        if FEATURE_DIRECTION in self.features:
            self.char_direction = serv.configure_char("RotationDirection", value=0)
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        if self.domain != "fan":
            if "Active" in values:
                self.turn(values["Active"] == 1, reset_char=self.char_active, off_value=0)
            return

        if values.get("Active") == 0 or values.get("RotationSpeed") == 0:
            self.call_service("fan", "turn_off")
            return
        if "RotationSpeed" in values:
            self.call_service("fan", "set_percentage", {"percentage": values["RotationSpeed"]})
        elif values.get("Active") == 1:
            self.call_service("fan", "turn_on")
        if "SwingMode" in values:
            self.call_service("fan", "oscillate", {"oscillating": values["SwingMode"] == 1})
        if "RotationDirection" in values:
            direction = "reverse" if values["RotationDirection"] == 1 else "forward"
            self.call_service("fan", "set_direction", {"direction": direction})

    def async_update(self, state: State) -> None:
        on = is_on(state)
        if self.momentary:
            return
        self.set_char(self.char_active, 1 if on else 0)
        if self.domain != "fan":
            return
        attrs = state.attributes
        if self.char_speed is not None and on:
            pct = to_float(attrs.get("percentage"))
            if pct is not None:
                self.set_char(self.char_speed, pct)
        if self.char_swing is not None:
            self.set_char(self.char_swing, 1 if attrs.get("oscillating") else 0)
        if self.char_direction is not None:
            self.set_char(
                self.char_direction, 1 if attrs.get("direction") == "reverse" else 0
            )

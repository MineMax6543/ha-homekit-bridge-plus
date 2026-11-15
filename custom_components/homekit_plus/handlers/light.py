"""Light bulb handler with selectable brightness / color temp / color."""

from __future__ import annotations

from typing import Any

from pyhap.const import CATEGORY_LIGHTBULB

from homeassistant.core import State

from ..const import FEATURE_BRIGHTNESS, FEATURE_COLOR, FEATURE_COLOR_TEMP
from ..util import clamp, is_on, resolve_features, to_float
from .base import Handler

_COLOR_MODES = {"hs", "xy", "rgb", "rgbw", "rgbww"}
_BRIGHTNESS_MODES = _COLOR_MODES | {"brightness", "color_temp", "white"}


def _supported(state: State) -> set[str]:
    """Features the light actually supports."""
    if state.domain != "light":
        return set()
    modes = set(state.attributes.get("supported_color_modes") or [])
    result: set[str] = set()
    if modes & _BRIGHTNESS_MODES:
        result.add(FEATURE_BRIGHTNESS)
    if "color_temp" in modes:
        result.add(FEATURE_COLOR_TEMP)
    if modes & _COLOR_MODES:
        result.add(FEATURE_COLOR)
    return result


class LightHandler(Handler):
    """HomeKit Lightbulb. Also usable for switches ("show switch as light")."""

    category = CATEGORY_LIGHTBULB

    def setup(self, state: State) -> None:
        self.features = resolve_features(self.acc_type, self.cfg) & _supported(state)
        chars = ["On"]
        if FEATURE_BRIGHTNESS in self.features:
            chars.append("Brightness")
        if FEATURE_COLOR_TEMP in self.features:
            chars.append("ColorTemperature")
        if FEATURE_COLOR in self.features:
            chars += ["Hue", "Saturation"]
        serv = self.add_service("Lightbulb", chars)
        self.char_on = serv.configure_char("On", value=False)
        self.char_brightness = (
            serv.configure_char("Brightness", value=100)
            if FEATURE_BRIGHTNESS in self.features
            else None
        )
        self.char_ct = None
        if FEATURE_COLOR_TEMP in self.features:
            attrs = state.attributes
            min_k = to_float(attrs.get("min_color_temp_kelvin")) or 2000
            max_k = to_float(attrs.get("max_color_temp_kelvin")) or 6500
            min_mired = int(1_000_000 / max_k)
            max_mired = int(round(1_000_000 / min_k))
            self.char_ct = serv.configure_char(
                "ColorTemperature",
                properties={"minValue": min_mired, "maxValue": max_mired},
                value=min_mired,
            )
        self.char_hue = self.char_sat = None
        if FEATURE_COLOR in self.features:
            self.char_hue = serv.configure_char("Hue", value=0)
            self.char_sat = serv.configure_char("Saturation", value=0)
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        if self.domain != "light":
            if "On" in values:
                self.turn(bool(values["On"]), reset_char=self.char_on, off_value=False)
            return

        if values.get("On") is False or values.get("Brightness") == 0:
            self.call_service("light", "turn_off")
            return

        data: dict[str, Any] = {}
        if "Brightness" in values:
            data["brightness_pct"] = values["Brightness"]
        if "Hue" in values or "Saturation" in values:
            hue = values.get("Hue", self.char_hue.value if self.char_hue else 0)
            sat = values.get("Saturation", self.char_sat.value if self.char_sat else 0)
            data["hs_color"] = (hue, sat)
        elif "ColorTemperature" in values and values["ColorTemperature"]:
            data["color_temp_kelvin"] = int(round(1_000_000 / values["ColorTemperature"]))
        if data or values.get("On") is True:
            self.call_service("light", "turn_on", data)

    def async_update(self, state: State) -> None:
        on = is_on(state)
        self.set_char(self.char_on, on)
        if self.domain != "light" or not on:
            return
        attrs = state.attributes
        if self.char_brightness is not None:
            brightness = to_float(attrs.get("brightness"))
            if brightness is not None:
                self.set_char(
                    self.char_brightness, int(clamp(round(brightness / 255 * 100), 1, 100))
                )
        if self.char_ct is not None:
            kelvin = to_float(attrs.get("color_temp_kelvin"))
            if kelvin:
                props = self.char_ct.properties
                mired = int(round(1_000_000 / kelvin))
                self.set_char(
                    self.char_ct, int(clamp(mired, props["minValue"], props["maxValue"]))
                )
        if self.char_hue is not None:
            hs = attrs.get("hs_color")
            if hs and len(hs) == 2:
                self.set_char(self.char_hue, round(float(hs[0]), 1))
                self.set_char(self.char_sat, round(float(hs[1]), 1))

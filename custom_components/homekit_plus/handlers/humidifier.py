"""Humidifier / dehumidifier handler."""

from __future__ import annotations

from typing import Any

from pyhap.const import CATEGORY_DEHUMIDIFIER, CATEGORY_HUMIDIFIER

from homeassistant.core import State

from ..const import CONF_LINKED_HUMIDITY, FEATURE_TARGET_HUMIDITY
from ..util import clamp, is_on, resolve_features, to_float
from .base import Handler

_INACTIVE, _IDLE, _HUMIDIFYING, _DEHUMIDIFYING = 0, 1, 2, 3


class HumidifierHandler(Handler):
    """HumidifierDehumidifier service."""

    def setup(self, state: State) -> None:
        attrs = state.attributes
        self.dehumidifier = attrs.get("device_class") == "dehumidifier"
        self.category = CATEGORY_DEHUMIDIFIER if self.dehumidifier else CATEGORY_HUMIDIFIER
        self.hk_mode = 2 if self.dehumidifier else 1
        self.working_state = _DEHUMIDIFYING if self.dehumidifier else _HUMIDIFYING
        self.use_target = (
            FEATURE_TARGET_HUMIDITY in resolve_features(self.acc_type, self.cfg)
            and self.domain == "humidifier"
        )
        self.threshold_name = (
            "RelativeHumidityDehumidifierThreshold"
            if self.dehumidifier
            else "RelativeHumidityHumidifierThreshold"
        )
        chars = [
            "Active",
            "CurrentRelativeHumidity",
            "CurrentHumidifierDehumidifierState",
            "TargetHumidifierDehumidifierState",
        ]
        if self.use_target:
            chars.append(self.threshold_name)
        serv = self.add_service("HumidifierDehumidifier", chars)
        self.char_active = serv.configure_char("Active", value=0)
        # Fed by the linked humidity sensor instead, if configured
        self.linked_humidity_char = serv.configure_char("CurrentRelativeHumidity", value=0)
        self.has_linked_humidity = bool(self.cfg.get(CONF_LINKED_HUMIDITY))
        self.char_current = serv.configure_char(
            "CurrentHumidifierDehumidifierState",
            valid_values={
                "Inactive": _INACTIVE,
                "Idle": _IDLE,
                "Working": self.working_state,
            },
            value=_INACTIVE,
        )
        mode_label = "Dehumidifier" if self.dehumidifier else "Humidifier"
        serv.configure_char(
            "TargetHumidifierDehumidifierState",
            valid_values={mode_label: self.hk_mode},
            value=self.hk_mode,
        )
        self.char_target = None
        if self.use_target:
            low = to_float(attrs.get("min_humidity")) or 0
            high = to_float(attrs.get("max_humidity")) or 100
            self.char_target = serv.configure_char(
                self.threshold_name,
                properties={"minValue": low, "maxValue": high},
                value=low,
            )
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        if "Active" in values:
            self.turn(values["Active"] == 1, reset_char=self.char_active, off_value=0)
        if self.threshold_name in values and self.use_target:
            self.call_service(
                "humidifier", "set_humidity", {"humidity": int(values[self.threshold_name])}
            )

    def async_update(self, state: State) -> None:
        if self.momentary:
            return
        on = is_on(state)
        attrs = state.attributes
        self.set_char(self.char_active, 1 if on else 0)
        action = attrs.get("action")
        current = {
            "off": _INACTIVE,
            "idle": _IDLE,
            "humidifying": self.working_state,
            "drying": self.working_state,
        }.get(action, self.working_state if on else _INACTIVE)
        self.set_char(self.char_current, current)
        if not self.has_linked_humidity:
            humidity = to_float(attrs.get("current_humidity"))
            if humidity is not None:
                self.set_char(self.linked_humidity_char, clamp(humidity, 0, 100))
        if self.char_target is not None:
            target = to_float(attrs.get("humidity"))
            if target is not None:
                props = self.char_target.properties
                self.set_char(
                    self.char_target, clamp(target, props["minValue"], props["maxValue"])
                )

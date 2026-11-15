"""Cover handlers: window covering / door / window, and garage door."""

from __future__ import annotations

from typing import Any

from pyhap.const import (
    CATEGORY_DOOR,
    CATEGORY_GARAGE_DOOR_OPENER,
    CATEGORY_WINDOW,
    CATEGORY_WINDOW_COVERING,
)

from homeassistant.core import State

from ..const import FEATURE_POSITION, FEATURE_TILT, TYPE_DOOR, TYPE_WINDOW
from ..util import clamp, is_on, resolve_features, to_float
from .base import Handler

# CoverEntityFeature bit flags
_SET_POSITION = 4
_SET_TILT_POSITION = 128

_SERVICE_FOR_TYPE = {TYPE_DOOR: "Door", TYPE_WINDOW: "Window"}
_CATEGORY_FOR_TYPE = {TYPE_DOOR: CATEGORY_DOOR, TYPE_WINDOW: CATEGORY_WINDOW}


class PositionCoverHandler(Handler):
    """WindowCovering / Door / Window."""

    def setup(self, state: State) -> None:
        self.category = _CATEGORY_FOR_TYPE.get(self.acc_type, CATEGORY_WINDOW_COVERING)
        flags = int(state.attributes.get("supported_features") or 0)
        wanted = resolve_features(self.acc_type, self.cfg)
        self.use_position = FEATURE_POSITION in wanted and bool(flags & _SET_POSITION)
        self.use_tilt = (
            FEATURE_TILT in wanted
            and bool(flags & _SET_TILT_POSITION)
            and self.acc_type not in _SERVICE_FOR_TYPE
        )
        chars = ["CurrentPosition", "TargetPosition", "PositionState"]
        if self.use_tilt:
            chars += ["CurrentHorizontalTiltAngle", "TargetHorizontalTiltAngle"]
        serv = self.add_service(_SERVICE_FOR_TYPE.get(self.acc_type, "WindowCovering"), chars)
        self.char_current = serv.configure_char("CurrentPosition", value=0)
        target_props = None if self.use_position else {"minStep": 100}
        self.char_target = serv.configure_char(
            "TargetPosition", properties=target_props, value=0
        )
        self.char_state = serv.configure_char("PositionState", value=2)
        self.char_tilt_current = self.char_tilt_target = None
        if self.use_tilt:
            self.char_tilt_current = serv.configure_char("CurrentHorizontalTiltAngle", value=0)
            self.char_tilt_target = serv.configure_char("TargetHorizontalTiltAngle", value=0)
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        if "TargetPosition" in values:
            target = values["TargetPosition"]
            if self.use_position:
                self.call_service("cover", "set_cover_position", {"position": target})
            else:
                self.call_service("cover", "open_cover" if target >= 50 else "close_cover")
        if "TargetHorizontalTiltAngle" in values:
            tilt = round((values["TargetHorizontalTiltAngle"] + 90) / 1.8)
            self.call_service(
                "cover", "set_cover_tilt_position", {"tilt_position": int(clamp(tilt, 0, 100))}
            )

    def async_update(self, state: State) -> None:
        attrs = state.attributes
        position = to_float(attrs.get("current_position")) if self.use_position else None
        if position is None:
            position = 100 if is_on(state) else 0
        position = int(position)
        self.set_char(self.char_current, position)
        if state.state == "opening":
            self.set_char(self.char_state, 1)
            if not self.use_position:
                self.set_char(self.char_target, 100)
        elif state.state == "closing":
            self.set_char(self.char_state, 0)
            if not self.use_position:
                self.set_char(self.char_target, 0)
        else:
            self.set_char(self.char_state, 2)
            self.set_char(self.char_target, position)
        if self.char_tilt_current is not None:
            tilt = to_float(attrs.get("current_tilt_position"))
            if tilt is not None:
                angle = int(round(tilt * 1.8 - 90))
                self.set_char(self.char_tilt_current, angle)
                self.set_char(self.char_tilt_target, angle)


class GarageDoorHandler(Handler):
    """GarageDoorOpener."""

    category = CATEGORY_GARAGE_DOOR_OPENER

    def setup(self, state: State) -> None:
        serv = self.add_service(
            "GarageDoorOpener", ["CurrentDoorState", "TargetDoorState", "ObstructionDetected"]
        )
        self.char_current = serv.configure_char("CurrentDoorState", value=1)
        self.char_target = serv.configure_char("TargetDoorState", value=1)
        serv.configure_char("ObstructionDetected", value=False)
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        if "TargetDoorState" in values:
            opening = values["TargetDoorState"] == 0
            self.call_service("cover", "open_cover" if opening else "close_cover")

    def async_update(self, state: State) -> None:
        current = {"open": 0, "closed": 1, "opening": 2, "closing": 3}.get(state.state)
        if current is None:
            return
        self.set_char(self.char_current, current)
        self.set_char(self.char_target, 0 if current in (0, 2) else 1)

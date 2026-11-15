"""Lock and security system handlers."""

from __future__ import annotations

from typing import Any

from pyhap.const import CATEGORY_ALARM_SYSTEM, CATEGORY_DOOR_LOCK

from homeassistant.core import State

from ..const import ALARM_MODE_OPTIONS, CONF_ALARM_MODES, CONF_CODE
from .base import Handler


class LockHandler(Handler):
    """LockMechanism."""

    category = CATEGORY_DOOR_LOCK

    def setup(self, state: State) -> None:
        serv = self.add_service("LockMechanism", ["LockCurrentState", "LockTargetState"])
        self.char_current = serv.configure_char("LockCurrentState", value=3)
        self.char_target = serv.configure_char("LockTargetState", value=1)
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        if "LockTargetState" not in values:
            return
        data = {"code": self.cfg[CONF_CODE]} if self.cfg.get(CONF_CODE) else {}
        self.call_service("lock", "lock" if values["LockTargetState"] == 1 else "unlock", data)

    def async_update(self, state: State) -> None:
        value = state.state
        current = {"locked": 1, "unlocked": 0, "open": 0, "jammed": 2}.get(value)
        if current is not None:
            self.set_char(self.char_current, current)
        elif value not in ("locking", "unlocking", "opening"):
            self.set_char(self.char_current, 3)
        target = {
            "locked": 1, "locking": 1, "unlocked": 0, "unlocking": 0, "open": 0, "opening": 0,
        }.get(value)
        if target is not None:
            self.set_char(self.char_target, target)


# AlarmControlPanelEntityFeature bit flags
_ARM_HOME = 1
_ARM_AWAY = 2
_ARM_NIGHT = 4

_HK_STAY, _HK_AWAY, _HK_NIGHT, _HK_DISARM, _HK_TRIGGERED = 0, 1, 2, 3, 4
_MODE_TO_HK = {"stay": _HK_STAY, "away": _HK_AWAY, "night": _HK_NIGHT}
_MODE_TO_FLAG = {"stay": _ARM_HOME, "away": _ARM_AWAY, "night": _ARM_NIGHT}
_HK_TO_SERVICE = {
    _HK_STAY: "alarm_arm_home",
    _HK_AWAY: "alarm_arm_away",
    _HK_NIGHT: "alarm_arm_night",
    _HK_DISARM: "alarm_disarm",
}
_STATE_TO_CURRENT = {
    "armed_home": _HK_STAY,
    "armed_custom_bypass": _HK_STAY,
    "armed_away": _HK_AWAY,
    "armed_vacation": _HK_AWAY,
    "armed_night": _HK_NIGHT,
    "disarmed": _HK_DISARM,
    "triggered": _HK_TRIGGERED,
}
_STATE_TO_TARGET = {
    "armed_home": _HK_STAY,
    "armed_custom_bypass": _HK_STAY,
    "armed_away": _HK_AWAY,
    "armed_vacation": _HK_AWAY,
    "armed_night": _HK_NIGHT,
    "disarmed": _HK_DISARM,
    "disarming": _HK_DISARM,
}


class SecuritySystemHandler(Handler):
    """SecuritySystem with selectable arm modes."""

    category = CATEGORY_ALARM_SYSTEM

    def setup(self, state: State) -> None:
        flags = int(state.attributes.get("supported_features") or 0)
        wanted = self.cfg.get(CONF_ALARM_MODES) or ALARM_MODE_OPTIONS
        modes = [m for m in ALARM_MODE_OPTIONS if m in wanted and flags & _MODE_TO_FLAG[m]]
        target_valid = {m: _MODE_TO_HK[m] for m in modes} | {"Disarm": _HK_DISARM}
        current_valid = {m: _MODE_TO_HK[m] for m in modes} | {
            "Disarmed": _HK_DISARM,
            "AlarmTriggered": _HK_TRIGGERED,
        }
        serv = self.add_service(
            "SecuritySystem", ["SecuritySystemCurrentState", "SecuritySystemTargetState"]
        )
        self.char_current = serv.configure_char(
            "SecuritySystemCurrentState", valid_values=current_valid, value=_HK_DISARM
        )
        self.char_target = serv.configure_char(
            "SecuritySystemTargetState", valid_values=target_valid, value=_HK_DISARM
        )
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        target = values.get("SecuritySystemTargetState")
        if target is None:
            return
        data = {"code": self.cfg[CONF_CODE]} if self.cfg.get(CONF_CODE) else {}
        self.call_service("alarm_control_panel", _HK_TO_SERVICE[target], data)

    def async_update(self, state: State) -> None:
        current = _STATE_TO_CURRENT.get(state.state)
        if current is not None:
            self.set_char(self.char_current, current)
        target = _STATE_TO_TARGET.get(state.state)
        if target is not None:
            self.set_char(self.char_target, target)

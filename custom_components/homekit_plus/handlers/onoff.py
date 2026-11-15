"""Switch, outlet and valve handlers (generic on/off)."""

from __future__ import annotations

from typing import Any

from pyhap.const import (
    CATEGORY_FAUCET,
    CATEGORY_OUTLET,
    CATEGORY_SHOWER_HEAD,
    CATEGORY_SPRINKLER,
    CATEGORY_SWITCH,
)

from homeassistant.core import State

from ..const import FEATURE_OUTLET_IN_USE, TYPE_FAUCET, TYPE_SHOWER, TYPE_SPRINKLER
from ..util import VALVE_TYPE_VALUES, is_on, resolve_features
from .base import Handler


class SwitchHandler(Handler):
    """HomeKit Switch."""

    category = CATEGORY_SWITCH

    def setup(self, state: State) -> None:
        serv = self.add_service("Switch", ["On"])
        self.char_on = serv.configure_char("On", value=False)
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        if "On" in values:
            self.turn(bool(values["On"]), reset_char=self.char_on, off_value=False)

    def async_update(self, state: State) -> None:
        if not self.momentary:
            self.set_char(self.char_on, is_on(state))


class OutletHandler(Handler):
    """HomeKit Outlet."""

    category = CATEGORY_OUTLET

    def setup(self, state: State) -> None:
        self.report_in_use = FEATURE_OUTLET_IN_USE in resolve_features(
            self.acc_type, self.cfg
        )
        serv = self.add_service("Outlet", ["On", "OutletInUse"])
        self.char_on = serv.configure_char("On", value=False)
        self.char_in_use = serv.configure_char("OutletInUse", value=True)
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        if "On" in values:
            self.turn(bool(values["On"]), reset_char=self.char_on, off_value=False)

    def async_update(self, state: State) -> None:
        if self.momentary:
            return
        on = is_on(state)
        self.set_char(self.char_on, on)
        self.set_char(self.char_in_use, on if self.report_in_use else True)


class ValveHandler(Handler):
    """HomeKit Valve (generic, sprinkler, shower head, faucet)."""

    def setup(self, state: State) -> None:
        self.category = {
            TYPE_SPRINKLER: CATEGORY_SPRINKLER,
            TYPE_SHOWER: CATEGORY_SHOWER_HEAD,
            TYPE_FAUCET: CATEGORY_FAUCET,
        }.get(self.acc_type, CATEGORY_FAUCET)
        serv = self.add_service("Valve", ["Active", "InUse", "ValveType"])
        self.char_active = serv.configure_char("Active", value=0)
        self.char_in_use = serv.configure_char("InUse", value=0)
        serv.configure_char("ValveType", value=VALVE_TYPE_VALUES[self.acc_type])
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        if "Active" in values:
            on = values["Active"] == 1
            if not self.momentary:
                self.set_char(self.char_in_use, 1 if on else 0)
            self.turn(on, reset_char=self.char_active, off_value=0)

    def async_update(self, state: State) -> None:
        if self.momentary:
            return
        value = 1 if is_on(state) else 0
        self.set_char(self.char_active, value)
        self.set_char(self.char_in_use, value)

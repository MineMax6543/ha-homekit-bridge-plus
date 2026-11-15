"""Thermostat handler with selectable HVAC modes."""

from __future__ import annotations

from typing import Any

from pyhap.const import CATEGORY_HEATER, CATEGORY_THERMOSTAT

from homeassistant.const import UnitOfTemperature
from homeassistant.core import State
from homeassistant.util.unit_conversion import TemperatureConverter

from ..const import (
    CONF_HVAC_MODES,
    CONF_LINKED_HUMIDITY,
    FEATURE_HUMIDITY,
    FEATURE_TEMP_RANGE,
    HVAC_MODE_OPTIONS,
)
from ..util import clamp, resolve_features, to_float
from .base import Handler

# ClimateEntityFeature bit flags
_TARGET_TEMPERATURE = 1
_TARGET_TEMPERATURE_RANGE = 2

_HK_OFF, _HK_HEAT, _HK_COOL, _HK_AUTO = 0, 1, 2, 3
_OPTION_TO_HK = {"off": _HK_OFF, "heat": _HK_HEAT, "cool": _HK_COOL, "auto": _HK_AUTO}
_HK_LABEL = {_HK_OFF: "Off", _HK_HEAT: "Heat", _HK_COOL: "Cool", _HK_AUTO: "Auto"}


class ThermostatHandler(Handler):
    """HomeKit Thermostat."""

    category = CATEGORY_THERMOSTAT

    def setup(self, state: State) -> None:
        attrs = state.attributes
        self.unit = self.hass.config.units.temperature_unit
        flags = int(attrs.get("supported_features") or 0)
        features = resolve_features(self.acc_type, self.cfg)
        ha_modes: list[str] = list(attrs.get("hvac_modes") or [])

        # HomeKit mode -> HA mode
        self.hk_to_ha: dict[int, str] = {}
        if "off" in ha_modes:
            self.hk_to_ha[_HK_OFF] = "off"
        if "heat" in ha_modes:
            self.hk_to_ha[_HK_HEAT] = "heat"
        if "cool" in ha_modes:
            self.hk_to_ha[_HK_COOL] = "cool"
        for candidate in ("heat_cool", "auto"):
            if candidate in ha_modes:
                self.hk_to_ha[_HK_AUTO] = candidate
                break
        wanted = {
            _OPTION_TO_HK[m] for m in (self.cfg.get(CONF_HVAC_MODES) or HVAC_MODE_OPTIONS)
        }
        allowed = {hk: ha for hk, ha in self.hk_to_ha.items() if hk in wanted}
        if not allowed:  # never leave HomeKit without a valid mode
            allowed = dict(self.hk_to_ha) or {_HK_HEAT: "heat"}
        self.hk_to_ha = allowed

        self.use_range = (
            FEATURE_TEMP_RANGE in features
            and bool(flags & _TARGET_TEMPERATURE_RANGE)
            and _HK_AUTO in allowed
        )
        self.has_linked_humidity = bool(self.cfg.get(CONF_LINKED_HUMIDITY))
        self.use_humidity = self.has_linked_humidity or (
            FEATURE_HUMIDITY in features and "current_humidity" in attrs
        )

        chars = [
            "CurrentHeatingCoolingState",
            "TargetHeatingCoolingState",
            "CurrentTemperature",
            "TargetTemperature",
            "TemperatureDisplayUnits",
        ]
        if self.use_range:
            chars += ["HeatingThresholdTemperature", "CoolingThresholdTemperature"]
        if self.use_humidity:
            chars.append("CurrentRelativeHumidity")
        serv = self.add_service("Thermostat", chars)

        min_c = self._to_c(to_float(attrs.get("min_temp")) or self._from_c(7))
        max_c = self._to_c(to_float(attrs.get("max_temp")) or self._from_c(35))
        step = to_float(attrs.get("target_temp_step")) or 0.5
        if self.unit == UnitOfTemperature.FAHRENHEIT:
            step = 0.1
        temp_props = {"minValue": round(min_c, 1), "maxValue": round(max_c, 1), "minStep": step}

        current_valid = {"Off": _HK_OFF, "Heat": _HK_HEAT, "Cool": _HK_COOL}
        target_valid = {_HK_LABEL[hk]: hk for hk in sorted(allowed)}
        self.char_current_state = serv.configure_char(
            "CurrentHeatingCoolingState", valid_values=current_valid, value=_HK_OFF
        )
        self.char_target_state = serv.configure_char(
            "TargetHeatingCoolingState", valid_values=target_valid
        )
        self.char_current_temp = serv.configure_char("CurrentTemperature", value=21.0)
        self.char_target_temp = serv.configure_char(
            "TargetTemperature", properties=temp_props, value=21.0
        )
        serv.configure_char(
            "TemperatureDisplayUnits",
            value=1 if self.unit == UnitOfTemperature.FAHRENHEIT else 0,
        )
        self.char_heat = self.char_cool = self.char_humidity = None
        self.linked_humidity_char = None
        if self.use_range:
            self.char_heat = serv.configure_char(
                "HeatingThresholdTemperature", properties=temp_props, value=round(min_c, 1)
            )
            self.char_cool = serv.configure_char(
                "CoolingThresholdTemperature", properties=temp_props, value=round(max_c, 1)
            )
        if self.use_humidity:
            self.char_humidity = serv.configure_char("CurrentRelativeHumidity", value=50)
            if self.has_linked_humidity:
                # fed by the linked humidity sensor (see bridge._add_linked)
                self.linked_humidity_char = self.char_humidity
        serv.setter_callback = self.on_setter(self._set)

    # ---- unit helpers -----------------------------------------------------
    def _to_c(self, value: float) -> float:
        if self.unit == UnitOfTemperature.FAHRENHEIT:
            return TemperatureConverter.convert(
                value, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            )
        return value

    def _from_c(self, value: float) -> float:
        if self.unit == UnitOfTemperature.FAHRENHEIT:
            return round(
                TemperatureConverter.convert(
                    value, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
                )
            )
        return value

    # ---- HomeKit -> HA ----------------------------------------------------
    def _set(self, values: dict[str, Any]) -> None:
        if "TargetHeatingCoolingState" in values:
            mode = self.hk_to_ha.get(values["TargetHeatingCoolingState"])
            if mode:
                self.call_service("climate", "set_hvac_mode", {"hvac_mode": mode})
        if "TargetTemperature" in values:
            self.call_service(
                "climate",
                "set_temperature",
                {"temperature": self._from_c(values["TargetTemperature"])},
            )
        if "HeatingThresholdTemperature" in values or "CoolingThresholdTemperature" in values:
            low = values.get("HeatingThresholdTemperature", self.char_heat.value)
            high = values.get("CoolingThresholdTemperature", self.char_cool.value)
            self.call_service(
                "climate",
                "set_temperature",
                {"target_temp_low": self._from_c(low), "target_temp_high": self._from_c(high)},
            )

    # ---- HA -> HomeKit ----------------------------------------------------
    def async_update(self, state: State) -> None:
        attrs = state.attributes
        ha_mode = state.state
        hk_mode = next((hk for hk, ha in self.hk_to_ha.items() if ha == ha_mode), None)
        if hk_mode is None and ha_mode in ("dry", "fan_only"):
            hk_mode = _HK_COOL if _HK_COOL in self.hk_to_ha else _HK_AUTO
        if hk_mode is not None and hk_mode in self.hk_to_ha:
            self.set_char(self.char_target_state, hk_mode)

        action = attrs.get("hvac_action")
        current = {"heating": _HK_HEAT, "preheating": _HK_HEAT, "cooling": _HK_COOL}.get(
            action, _HK_OFF
        )
        if action is None and ha_mode in ("heat", "cool"):
            current = _HK_HEAT if ha_mode == "heat" else _HK_COOL
        self.set_char(self.char_current_state, current)

        temp = to_float(attrs.get("current_temperature"))
        if temp is not None:
            self.set_char(self.char_current_temp, round(self._to_c(temp), 1))
        target = to_float(attrs.get("temperature"))
        if target is not None:
            self.set_char(self.char_target_temp, self._clamp(self._to_c(target)))
        if self.use_range:
            low = to_float(attrs.get("target_temp_low"))
            high = to_float(attrs.get("target_temp_high"))
            if low is not None:
                self.set_char(self.char_heat, self._clamp(self._to_c(low)))
                if target is None:
                    self.set_char(self.char_target_temp, self._clamp(self._to_c(low)))
            if high is not None:
                self.set_char(self.char_cool, self._clamp(self._to_c(high)))
        if self.char_humidity is not None and not self.has_linked_humidity:
            humidity = to_float(attrs.get("current_humidity"))
            if humidity is not None:
                self.set_char(self.char_humidity, clamp(humidity, 0, 100))

    def _clamp(self, value: float) -> float:
        props = self.char_target_temp.properties
        return round(clamp(value, props["minValue"], props["maxValue"]), 1)


class WaterHeaterHandler(Handler):
    """Water heater shown as a heat-only thermostat (optionally with Off)."""

    category = CATEGORY_HEATER

    _to_c = ThermostatHandler._to_c
    _from_c = ThermostatHandler._from_c

    def setup(self, state: State) -> None:
        attrs = state.attributes
        self.unit = self.hass.config.units.temperature_unit
        operations = list(attrs.get("operation_list") or [])
        self.heat_operation = next((op for op in operations if op != "off"), None)
        self.can_off = "off" in operations
        serv = self.add_service(
            "Thermostat",
            [
                "CurrentHeatingCoolingState",
                "TargetHeatingCoolingState",
                "CurrentTemperature",
                "TargetTemperature",
                "TemperatureDisplayUnits",
            ],
        )
        min_c = self._to_c(to_float(attrs.get("min_temp")) or self._from_c(30))
        max_c = self._to_c(to_float(attrs.get("max_temp")) or self._from_c(70))
        target_valid = {"Heat": _HK_HEAT}
        if self.can_off:
            target_valid["Off"] = _HK_OFF
        self.char_current_state = serv.configure_char(
            "CurrentHeatingCoolingState",
            valid_values={"Off": _HK_OFF, "Heat": _HK_HEAT},
            value=_HK_HEAT,
        )
        self.char_target_state = serv.configure_char(
            "TargetHeatingCoolingState", valid_values=target_valid, value=_HK_HEAT
        )
        self.char_current_temp = serv.configure_char(
            "CurrentTemperature", value=round(min_c, 1)
        )
        self.char_target_temp = serv.configure_char(
            "TargetTemperature",
            properties={"minValue": round(min_c, 1), "maxValue": round(max_c, 1), "minStep": 0.5},
            value=round(min_c, 1),
        )
        serv.configure_char(
            "TemperatureDisplayUnits",
            value=1 if self.unit == UnitOfTemperature.FAHRENHEIT else 0,
        )
        serv.setter_callback = self.on_setter(self._set)

    def _set(self, values: dict[str, Any]) -> None:
        mode = values.get("TargetHeatingCoolingState")
        if mode == _HK_OFF and self.can_off:
            self.call_service("water_heater", "set_operation_mode", {"operation_mode": "off"})
        elif mode == _HK_HEAT and self.heat_operation and self.can_off:
            self.call_service(
                "water_heater", "set_operation_mode", {"operation_mode": self.heat_operation}
            )
        if "TargetTemperature" in values:
            self.call_service(
                "water_heater",
                "set_temperature",
                {"temperature": self._from_c(values["TargetTemperature"])},
            )

    def async_update(self, state: State) -> None:
        attrs = state.attributes
        heating = state.state != "off"
        self.set_char(self.char_current_state, _HK_HEAT if heating else _HK_OFF)
        if self.can_off:
            self.set_char(self.char_target_state, _HK_HEAT if heating else _HK_OFF)
        temp = to_float(attrs.get("current_temperature"))
        if temp is not None:
            self.set_char(self.char_current_temp, round(self._to_c(temp), 1))
        target = to_float(attrs.get("temperature"))
        if target is not None:
            props = self.char_target_temp.properties
            self.set_char(
                self.char_target_temp,
                round(clamp(self._to_c(target), props["minValue"], props["maxValue"]), 1),
            )

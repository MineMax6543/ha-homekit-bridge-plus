"""Sensor handlers: numeric sensors, binary sensors and linked services."""

from __future__ import annotations

from pyhap.const import CATEGORY_SENSOR

from homeassistant.const import UnitOfTemperature
from homeassistant.core import State
from homeassistant.util.unit_conversion import TemperatureConverter

from ..const import (
    CONF_CO2_THRESHOLD,
    CONF_INVERT,
    CONF_LOW_BATTERY_THRESHOLD,
    DEFAULT_CO2_THRESHOLD,
    DEFAULT_LOW_BATTERY_THRESHOLD,
    TYPE_AQI,
    TYPE_CARBON_MONOXIDE,
    TYPE_CONTACT,
    TYPE_LEAK,
    TYPE_MOTION,
    TYPE_OCCUPANCY,
    TYPE_PM10,
    TYPE_PM25,
    TYPE_SMOKE,
)
from ..util import clamp, is_available, is_on, to_float
from .base import Handler


class TemperatureHandler(Handler):
    """TemperatureSensor."""

    category = CATEGORY_SENSOR

    def setup(self, state: State) -> None:
        serv = self.add_service("TemperatureSensor", ["CurrentTemperature"])
        self.char = serv.configure_char(
            "CurrentTemperature", properties={"minValue": -270, "maxValue": 1000}
        )

    def async_update(self, state: State) -> None:
        value = to_float(state.state)
        if value is None:
            return
        unit = state.attributes.get("unit_of_measurement")
        if unit == UnitOfTemperature.FAHRENHEIT:
            value = TemperatureConverter.convert(
                value, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            )
        elif unit == UnitOfTemperature.KELVIN:
            value = TemperatureConverter.convert(
                value, UnitOfTemperature.KELVIN, UnitOfTemperature.CELSIUS
            )
        self.set_char(self.char, round(value, 1))


class HumidityHandler(Handler):
    """HumiditySensor (also used for linked humidity sensors)."""

    category = CATEGORY_SENSOR

    def setup(self, state: State) -> None:
        serv = self.add_service("HumiditySensor", ["CurrentRelativeHumidity"])
        self.char = serv.configure_char("CurrentRelativeHumidity")

    def async_update(self, state: State) -> None:
        value = to_float(state.state)
        if value is not None:
            self.set_char(self.char, round(clamp(value, 0, 100)))


class LightSensorHandler(Handler):
    """LightSensor (lux)."""

    category = CATEGORY_SENSOR

    def setup(self, state: State) -> None:
        serv = self.add_service("LightSensor", ["CurrentAmbientLightLevel"])
        self.char = serv.configure_char("CurrentAmbientLightLevel", value=1)

    def async_update(self, state: State) -> None:
        value = to_float(state.state)
        if value is not None:
            self.set_char(self.char, clamp(value, 0.0001, 100000))


class CO2Handler(Handler):
    """CarbonDioxideSensor with level and configurable 'detected' threshold."""

    category = CATEGORY_SENSOR

    def setup(self, state: State) -> None:
        self.threshold = float(self.cfg.get(CONF_CO2_THRESHOLD) or DEFAULT_CO2_THRESHOLD)
        serv = self.add_service(
            "CarbonDioxideSensor",
            ["CarbonDioxideDetected", "CarbonDioxideLevel", "CarbonDioxidePeakLevel"],
        )
        self.char_detected = serv.configure_char("CarbonDioxideDetected", value=0)
        self.char_level = serv.configure_char("CarbonDioxideLevel", value=0)
        self.char_peak = serv.configure_char("CarbonDioxidePeakLevel", value=0)

    def async_update(self, state: State) -> None:
        value = to_float(state.state)
        if value is None:
            return
        value = clamp(value, 0, 100000)
        self.set_char(self.char_level, value)
        if value > (self.char_peak.value or 0):
            self.set_char(self.char_peak, value)
        self.set_char(self.char_detected, 1 if value > self.threshold else 0)


# (upper bound, HomeKit AirQuality value) - Excellent=1 .. Poor=5
_PM25_LEVELS = [(12, 1), (35.4, 2), (55.4, 3), (150.4, 4)]
_PM10_LEVELS = [(54, 1), (154, 2), (254, 3), (354, 4)]
_AQI_LEVELS = [(50, 1), (100, 2), (150, 3), (200, 4)]


class AirQualityHandler(Handler):
    """AirQualitySensor driven by PM2.5, PM10 or an AQI index."""

    category = CATEGORY_SENSOR

    def setup(self, state: State) -> None:
        self.density_char_name = {TYPE_PM25: "PM2.5Density", TYPE_PM10: "PM10Density"}.get(
            self.acc_type
        )
        self.levels = {TYPE_PM25: _PM25_LEVELS, TYPE_PM10: _PM10_LEVELS, TYPE_AQI: _AQI_LEVELS}[
            self.acc_type
        ]
        chars = ["AirQuality"]
        if self.density_char_name:
            chars.append(self.density_char_name)
        serv = self.add_service("AirQualitySensor", chars)
        self.char_quality = serv.configure_char("AirQuality", value=0)
        self.char_density = (
            serv.configure_char(self.density_char_name) if self.density_char_name else None
        )

    def async_update(self, state: State) -> None:
        value = to_float(state.state)
        if value is None:
            self.set_char(self.char_quality, 0)
            return
        quality = next((hk for bound, hk in self.levels if value <= bound), 5)
        self.set_char(self.char_quality, quality)
        if self.char_density is not None:
            self.set_char(self.char_density, clamp(value, 0, 1000))


# type -> (service, characteristic, value when detected, value when clear)
_BINARY: dict[str, tuple[str, str, object, object]] = {
    TYPE_MOTION: ("MotionSensor", "MotionDetected", True, False),
    TYPE_OCCUPANCY: ("OccupancySensor", "OccupancyDetected", 1, 0),
    # Contact: 0 = contact detected (closed), 1 = no contact (open)
    TYPE_CONTACT: ("ContactSensor", "ContactSensorState", 1, 0),
    TYPE_LEAK: ("LeakSensor", "LeakDetected", 1, 0),
    TYPE_SMOKE: ("SmokeSensor", "SmokeDetected", 1, 0),
    TYPE_CARBON_MONOXIDE: ("CarbonMonoxideSensor", "CarbonMonoxideDetected", 1, 0),
}


class BinaryHandler(Handler):
    """Any detected/not-detected sensor. Works for every on/off-ish entity."""

    category = CATEGORY_SENSOR

    def setup(self, state: State) -> None:
        service, char, self.on_value, self.off_value = _BINARY[self.acc_type]
        self.invert = bool(self.cfg.get(CONF_INVERT))
        serv = self.add_service(service, [char])
        self.char = serv.configure_char(char)

    def async_update(self, state: State) -> None:
        detected = is_on(state) != self.invert
        self.set_char(self.char, self.on_value if detected else self.off_value)


class BatteryHandler(Handler):
    """BatteryService fed by a linked battery sensor (numeric % or binary low)."""

    def setup(self, state: State) -> None:
        self.threshold = float(
            self.cfg.get(CONF_LOW_BATTERY_THRESHOLD) or DEFAULT_LOW_BATTERY_THRESHOLD
        )
        serv = self.add_service("BatteryService", ["BatteryLevel", "ChargingState", "StatusLowBattery"])
        self.char_level = serv.configure_char("BatteryLevel", value=100)
        serv.configure_char("ChargingState", value=2)  # not chargeable
        self.char_low = serv.configure_char("StatusLowBattery", value=0)

    def async_update(self, state: State) -> None:
        if not is_available(state):
            return
        if state.domain == "binary_sensor":
            low = state.state == "on"
            self.set_char(self.char_low, 1 if low else 0)
            self.set_char(self.char_level, 10 if low else 100)
            return
        level = to_float(state.state)
        if level is None:
            return
        level = int(clamp(round(level), 0, 100))
        self.set_char(self.char_level, level)
        self.set_char(self.char_low, 1 if level < self.threshold else 0)

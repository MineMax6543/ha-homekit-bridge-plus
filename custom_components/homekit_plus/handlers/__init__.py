"""Accessory type -> handler registry."""

from __future__ import annotations

from ..const import (
    TYPE_AQI,
    TYPE_CAMERA,
    TYPE_CARBON_MONOXIDE,
    TYPE_CO2,
    TYPE_CONTACT,
    TYPE_DOOR,
    TYPE_FAN,
    TYPE_FAUCET,
    TYPE_GARAGE_DOOR,
    TYPE_HUMIDIFIER,
    TYPE_HUMIDITY,
    TYPE_LEAK,
    TYPE_LIGHT_SENSOR,
    TYPE_LIGHTBULB,
    TYPE_LOCK,
    TYPE_MOTION,
    TYPE_OCCUPANCY,
    TYPE_OUTLET,
    TYPE_PM10,
    TYPE_PM25,
    TYPE_RECEIVER,
    TYPE_SECURITY_SYSTEM,
    TYPE_SHOWER,
    TYPE_SMOKE,
    TYPE_SPRINKLER,
    TYPE_SWITCH,
    TYPE_TELEVISION,
    TYPE_TEMPERATURE,
    TYPE_THERMOSTAT,
    TYPE_VALVE,
    TYPE_WATER_HEATER,
    TYPE_WINDOW,
    TYPE_WINDOW_COVERING,
)
from .base import Handler
from .camera import CameraHandler, CharFeedHandler, DoorbellHandler
from .climate import ThermostatHandler, WaterHeaterHandler
from .cover import GarageDoorHandler, PositionCoverHandler
from .fan import FanHandler
from .humidifier import HumidifierHandler
from .light import LightHandler
from .media import TelevisionHandler
from .onoff import OutletHandler, SwitchHandler, ValveHandler
from .security import LockHandler, SecuritySystemHandler
from .sensors import (
    AirQualityHandler,
    BatteryHandler,
    BinaryHandler,
    CO2Handler,
    HumidityHandler,
    LightSensorHandler,
    TemperatureHandler,
)

HANDLERS: dict[str, type[Handler]] = {
    TYPE_SWITCH: SwitchHandler,
    TYPE_OUTLET: OutletHandler,
    TYPE_VALVE: ValveHandler,
    TYPE_SPRINKLER: ValveHandler,
    TYPE_SHOWER: ValveHandler,
    TYPE_FAUCET: ValveHandler,
    TYPE_LIGHTBULB: LightHandler,
    TYPE_FAN: FanHandler,
    TYPE_WINDOW_COVERING: PositionCoverHandler,
    TYPE_DOOR: PositionCoverHandler,
    TYPE_WINDOW: PositionCoverHandler,
    TYPE_GARAGE_DOOR: GarageDoorHandler,
    TYPE_LOCK: LockHandler,
    TYPE_THERMOSTAT: ThermostatHandler,
    TYPE_SECURITY_SYSTEM: SecuritySystemHandler,
    TYPE_TEMPERATURE: TemperatureHandler,
    TYPE_HUMIDITY: HumidityHandler,
    TYPE_LIGHT_SENSOR: LightSensorHandler,
    TYPE_CO2: CO2Handler,
    TYPE_PM25: AirQualityHandler,
    TYPE_PM10: AirQualityHandler,
    TYPE_AQI: AirQualityHandler,
    TYPE_MOTION: BinaryHandler,
    TYPE_OCCUPANCY: BinaryHandler,
    TYPE_CONTACT: BinaryHandler,
    TYPE_LEAK: BinaryHandler,
    TYPE_SMOKE: BinaryHandler,
    TYPE_CARBON_MONOXIDE: BinaryHandler,
    TYPE_TELEVISION: TelevisionHandler,
    TYPE_RECEIVER: TelevisionHandler,
    TYPE_HUMIDIFIER: HumidifierHandler,
    TYPE_WATER_HEATER: WaterHeaterHandler,
    TYPE_CAMERA: CameraHandler,
}

__all__ = [
    "HANDLERS",
    "BatteryHandler",
    "BinaryHandler",
    "CharFeedHandler",
    "DoorbellHandler",
    "Handler",
    "HumidityHandler",
]

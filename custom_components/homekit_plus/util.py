"""Helpers shared by the bridge, the handlers and the config flow."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State, split_entity_id

from .const import (
    ACCESSORY_ONLY_TYPES,
    CONF_FEATURES,
    CONF_TYPE,
    DOMAIN_TYPES,
    TYPE_AQI,
    TYPE_CARBON_MONOXIDE,
    TYPE_CO2,
    TYPE_CONTACT,
    TYPE_DOOR,
    TYPE_FAUCET,
    TYPE_GARAGE_DOOR,
    TYPE_HUMIDITY,
    TYPE_LEAK,
    TYPE_LIGHT_SENSOR,
    TYPE_MOTION,
    TYPE_OCCUPANCY,
    TYPE_OUTLET,
    TYPE_PM10,
    TYPE_PM25,
    TYPE_RECEIVER,
    TYPE_SHOWER,
    TYPE_SMOKE,
    TYPE_SPRINKLER,
    TYPE_TELEVISION,
    TYPE_TEMPERATURE,
    TYPE_VALVE,
    TYPE_WINDOW,
    TYPE_FEATURES,
)

_INVALID_NAME_CHARS = re.compile(r"[^\w '’.,\-]", re.UNICODE)
_LEADING_INVALID = re.compile(r"^[^\w]+", re.UNICODE)
_TRAILING_INVALID = re.compile(r"[^\w.’']+$", re.UNICODE)


def cleanup_name(name: str | None, fallback: str = "Accessory") -> str:
    """Make a name acceptable for HomeKit (allowed chars, max 64 chars)."""
    name = _INVALID_NAME_CHARS.sub(" ", name or "")
    name = _LEADING_INVALID.sub("", name)
    name = _TRAILING_INVALID.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()[:64].strip()
    return name or fallback


def domain_of(entity_id: str) -> str:
    """Return the domain of an entity id."""
    return split_entity_id(entity_id)[0]


def is_available(state: State | None) -> bool:
    """Return True if the state is usable."""
    return state is not None and state.state != STATE_UNAVAILABLE


def is_on(state: State | None) -> bool:
    """Interpret a state as 'on' across domains."""
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return False
    domain = state.domain
    value = state.state
    if domain in ("cover", "valve"):
        return value in ("open", "opening")
    if domain == "vacuum":
        return value == "cleaning"
    if domain == "media_player":
        return value not in ("off", "standby")
    if domain == "climate":
        return value != "off"
    if domain == "lock":
        return value in ("unlocked", "open", "opening", "unlocking")
    if domain in ("person", "device_tracker"):
        return value == "home"
    return value == "on"


def to_float(value: Any) -> float | None:
    """Convert to float, returning None on failure."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def clamp(value: float, low: float, high: float) -> float:
    """Clamp a value into a range."""
    return max(low, min(high, value))


def allowed_types(entity_id: str, accessory_mode: bool = False) -> list[str]:
    """Accessory types offered for an entity in the given mode."""
    types = DOMAIN_TYPES.get(domain_of(entity_id), [])
    if accessory_mode:
        return list(types)
    return [t for t in types if t not in ACCESSORY_ONLY_TYPES]


def default_type(
    entity_id: str, state: State | None, accessory_mode: bool = False
) -> str | None:
    """Pick the most sensible accessory type for an entity."""
    domain = domain_of(entity_id)
    allowed = allowed_types(entity_id, accessory_mode)
    if not allowed:
        return None
    attrs = state.attributes if state else {}
    device_class = attrs.get("device_class")

    if domain == "binary_sensor":
        return {
            "motion": TYPE_MOTION,
            "moving": TYPE_MOTION,
            "vibration": TYPE_MOTION,
            "occupancy": TYPE_OCCUPANCY,
            "presence": TYPE_OCCUPANCY,
            "door": TYPE_CONTACT,
            "window": TYPE_CONTACT,
            "garage_door": TYPE_CONTACT,
            "opening": TYPE_CONTACT,
            "moisture": TYPE_LEAK,
            "smoke": TYPE_SMOKE,
            "gas": TYPE_CARBON_MONOXIDE,
            "carbon_monoxide": TYPE_CARBON_MONOXIDE,
        }.get(device_class, TYPE_OCCUPANCY)

    if domain == "sensor":
        unit = attrs.get("unit_of_measurement")
        by_class = {
            "temperature": TYPE_TEMPERATURE,
            "humidity": TYPE_HUMIDITY,
            "illuminance": TYPE_LIGHT_SENSOR,
            "carbon_dioxide": TYPE_CO2,
            "pm25": TYPE_PM25,
            "pm10": TYPE_PM10,
            "aqi": TYPE_AQI,
        }
        if device_class in by_class:
            return by_class[device_class]
        if unit in ("°C", "°F"):
            return TYPE_TEMPERATURE
        if unit == "lx":
            return TYPE_LIGHT_SENSOR
        if unit == "%" and "humid" in entity_id:
            return TYPE_HUMIDITY
        return None  # unknown sensor -> must be configured explicitly

    if domain == "media_player" and accessory_mode:
        if device_class in ("receiver", "speaker"):
            return TYPE_RECEIVER
        return TYPE_TELEVISION
    if domain == "switch" and device_class == "outlet":
        return TYPE_OUTLET
    if domain == "cover":
        if device_class in ("garage", "gate"):
            return TYPE_GARAGE_DOOR
        if device_class == "door":
            return TYPE_DOOR
        if device_class == "window":
            return TYPE_WINDOW
    if domain == "valve":
        return {"water": TYPE_FAUCET, "gas": TYPE_VALVE}.get(device_class, TYPE_VALVE)
    return allowed[0]


def resolve_type(
    entity_id: str,
    state: State | None,
    cfg: dict[str, Any],
    accessory_mode: bool = False,
) -> str | None:
    """Return the configured type if valid, else the default."""
    configured = cfg.get(CONF_TYPE)
    if configured in allowed_types(entity_id, accessory_mode):
        return configured
    return default_type(entity_id, state, accessory_mode)


def resolve_features(acc_type: str, cfg: dict[str, Any]) -> set[str]:
    """Return enabled features (all available features if unconfigured)."""
    available = TYPE_FEATURES.get(acc_type, [])
    configured = cfg.get(CONF_FEATURES)
    if configured is None:
        return set(available)
    return {f for f in configured if f in available}


VALVE_TYPE_VALUES = {TYPE_VALVE: 0, TYPE_SPRINKLER: 1, TYPE_SHOWER: 2, TYPE_FAUCET: 3}

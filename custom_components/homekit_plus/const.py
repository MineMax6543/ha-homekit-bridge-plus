"""Constants for HomeKit Bridge Plus."""

from __future__ import annotations

DOMAIN = "homekit_plus"
MANUFACTURER = "Home Assistant"
MODEL = "HomeKit Bridge Plus"

DEFAULT_NAME = "HA Bridge Plus"
DEFAULT_PORT = 21070
MAX_BRIDGED_ACCESSORIES = 150

# ---- Config entry data / options keys -------------------------------------
CONF_NAME = "name"
CONF_PORT = "port"
CONF_ADVERTISE_IP = "advertise_ip"
CONF_PIN = "pincode"
CONF_MODE = "mode"
CONF_ACCESSORY_ENTITY = "accessory_entity"
MODE_BRIDGE = "bridge"
MODE_ACCESSORY = "accessory"

CONF_ENTITIES = "entities"  # explicitly exposed entity ids
CONF_INCLUDE_LABELS = "include_labels"
CONF_INCLUDE_AREAS = "include_areas"
CONF_INCLUDE_DOMAINS = "include_domains"
CONF_EXCLUDE_ENTITIES = "exclude_entities"
CONF_ENTITY_CONFIG = "entity_config"  # {entity_id: {...}}
CONF_GROUPS = "groups"  # [{id, name, entities}]

# ---- Per entity config keys ------------------------------------------------
CONF_TYPE = "type"
CONF_FEATURES = "features"
CONF_LINKED_BATTERY = "linked_battery_sensor"
CONF_LOW_BATTERY_THRESHOLD = "low_battery_threshold"
CONF_LINKED_HUMIDITY = "linked_humidity_sensor"
CONF_INVERT = "invert"
CONF_CODE = "code"
CONF_HVAC_MODES = "hvac_modes"
CONF_ALARM_MODES = "alarm_modes"
CONF_CO2_THRESHOLD = "co2_threshold"
CONF_LINKED_MOTION = "linked_motion_sensor"
CONF_LINKED_DOORBELL = "linked_doorbell_sensor"
CONF_SOURCES = "sources"
CONF_VIDEO_CODEC = "video_codec"
CONF_SUPPORT_AUDIO = "support_audio"
CONF_STREAM_SOURCE = "stream_source"
CONF_MAX_WIDTH = "max_width"
CONF_MAX_HEIGHT = "max_height"
CONF_MAX_FPS = "max_fps"

# ---- Group keys ------------------------------------------------------------
CONF_GROUP_ID = "id"
CONF_GROUP_NAME = "name"
CONF_GROUP_ENTITIES = "entities"

# ---- Accessory types -------------------------------------------------------
TYPE_SWITCH = "switch"
TYPE_OUTLET = "outlet"
TYPE_VALVE = "valve"
TYPE_SPRINKLER = "sprinkler"
TYPE_SHOWER = "shower"
TYPE_FAUCET = "faucet"
TYPE_LIGHTBULB = "lightbulb"
TYPE_FAN = "fan"
TYPE_WINDOW_COVERING = "window_covering"
TYPE_GARAGE_DOOR = "garage_door"
TYPE_DOOR = "door"
TYPE_WINDOW = "window"
TYPE_LOCK = "lock"
TYPE_THERMOSTAT = "thermostat"
TYPE_SECURITY_SYSTEM = "security_system"
TYPE_TEMPERATURE = "temperature"
TYPE_HUMIDITY = "humidity"
TYPE_LIGHT_SENSOR = "light_sensor"
TYPE_CO2 = "co2"
TYPE_PM25 = "pm25"
TYPE_PM10 = "pm10"
TYPE_AQI = "aqi"
TYPE_MOTION = "motion"
TYPE_OCCUPANCY = "occupancy"
TYPE_CONTACT = "contact"
TYPE_LEAK = "leak"
TYPE_SMOKE = "smoke"
TYPE_CARBON_MONOXIDE = "carbon_monoxide"
TYPE_TELEVISION = "television"
TYPE_RECEIVER = "receiver"
TYPE_HUMIDIFIER = "humidifier"
TYPE_WATER_HEATER = "water_heater"
TYPE_CAMERA = "camera"

TYPE_LABELS: dict[str, str] = {
    TYPE_SWITCH: "Switch",
    TYPE_OUTLET: "Outlet",
    TYPE_VALVE: "Valve (generic)",
    TYPE_SPRINKLER: "Sprinkler",
    TYPE_SHOWER: "Shower head",
    TYPE_FAUCET: "Faucet",
    TYPE_LIGHTBULB: "Light bulb",
    TYPE_FAN: "Fan",
    TYPE_WINDOW_COVERING: "Window covering / blind",
    TYPE_GARAGE_DOOR: "Garage door",
    TYPE_DOOR: "Door",
    TYPE_WINDOW: "Window",
    TYPE_LOCK: "Lock",
    TYPE_THERMOSTAT: "Thermostat",
    TYPE_SECURITY_SYSTEM: "Security system",
    TYPE_TEMPERATURE: "Temperature sensor",
    TYPE_HUMIDITY: "Humidity sensor",
    TYPE_LIGHT_SENSOR: "Light (lux) sensor",
    TYPE_CO2: "CO2 sensor",
    TYPE_PM25: "Air quality (PM2.5)",
    TYPE_PM10: "Air quality (PM10)",
    TYPE_AQI: "Air quality (AQI index)",
    TYPE_MOTION: "Motion sensor",
    TYPE_OCCUPANCY: "Occupancy sensor",
    TYPE_CONTACT: "Contact sensor",
    TYPE_LEAK: "Leak sensor",
    TYPE_SMOKE: "Smoke sensor",
    TYPE_CARBON_MONOXIDE: "Carbon monoxide sensor",
    TYPE_TELEVISION: "Television (accessory mode only)",
    TYPE_RECEIVER: "Receiver / soundbar (accessory mode only)",
    TYPE_HUMIDIFIER: "Humidifier / dehumidifier",
    TYPE_WATER_HEATER: "Water heater",
    TYPE_CAMERA: "Camera",
}

# Apple only shows these properly when paired as their own accessory
ACCESSORY_ONLY_TYPES = {TYPE_TELEVISION, TYPE_RECEIVER}

# ---- Features (characteristics the user can switch on/off) -----------------
FEATURE_BRIGHTNESS = "brightness"
FEATURE_COLOR_TEMP = "color_temp"
FEATURE_COLOR = "color"
FEATURE_SPEED = "speed"
FEATURE_OSCILLATE = "oscillate"
FEATURE_DIRECTION = "direction"
FEATURE_POSITION = "position"
FEATURE_TILT = "tilt"
FEATURE_HUMIDITY = "humidity"
FEATURE_TEMP_RANGE = "temperature_range"
FEATURE_OUTLET_IN_USE = "outlet_in_use"
FEATURE_POWER = "power"
FEATURE_INPUTS = "inputs"
FEATURE_VOLUME = "volume"
FEATURE_MUTE = "mute"
FEATURE_PLAY_PAUSE = "play_pause"
FEATURE_REMOTE_EVENTS = "remote_events"
FEATURE_TARGET_HUMIDITY = "target_humidity"

FEATURE_LABELS: dict[str, str] = {
    FEATURE_BRIGHTNESS: "Brightness",
    FEATURE_COLOR_TEMP: "Color temperature",
    FEATURE_COLOR: "Color (hue / saturation)",
    FEATURE_SPEED: "Speed",
    FEATURE_OSCILLATE: "Oscillation",
    FEATURE_DIRECTION: "Direction",
    FEATURE_POSITION: "Exact position (otherwise open / close only)",
    FEATURE_TILT: "Tilt",
    FEATURE_HUMIDITY: "Current humidity",
    FEATURE_TEMP_RANGE: "Heat/cool temperature range",
    FEATURE_OUTLET_IN_USE: "Report 'in use' while on",
    FEATURE_POWER: "Power on/off",
    FEATURE_INPUTS: "Input selection",
    FEATURE_VOLUME: "Volume up/down (Control Center remote)",
    FEATURE_MUTE: "Mute",
    FEATURE_PLAY_PAUSE: "Play/pause (remote)",
    FEATURE_REMOTE_EVENTS: "Fire an event for remote arrow/select/back keys",
    FEATURE_TARGET_HUMIDITY: "Target humidity",
}

TYPE_FEATURES: dict[str, list[str]] = {
    TYPE_LIGHTBULB: [FEATURE_BRIGHTNESS, FEATURE_COLOR_TEMP, FEATURE_COLOR],
    TYPE_FAN: [FEATURE_SPEED, FEATURE_OSCILLATE, FEATURE_DIRECTION],
    TYPE_WINDOW_COVERING: [FEATURE_POSITION, FEATURE_TILT],
    TYPE_DOOR: [FEATURE_POSITION],
    TYPE_WINDOW: [FEATURE_POSITION],
    TYPE_THERMOSTAT: [FEATURE_HUMIDITY, FEATURE_TEMP_RANGE],
    TYPE_OUTLET: [FEATURE_OUTLET_IN_USE],
    TYPE_TELEVISION: [
        FEATURE_POWER,
        FEATURE_INPUTS,
        FEATURE_VOLUME,
        FEATURE_MUTE,
        FEATURE_PLAY_PAUSE,
        FEATURE_REMOTE_EVENTS,
    ],
    TYPE_HUMIDIFIER: [FEATURE_TARGET_HUMIDITY],
}
TYPE_FEATURES[TYPE_RECEIVER] = TYPE_FEATURES[TYPE_TELEVISION]

VIDEO_CODECS = ["libx264", "copy", "h264_v4l2m2m", "h264_omx", "h264_qsv"]
DEFAULT_MAX_WIDTH = 1920
DEFAULT_MAX_HEIGHT = 1080
DEFAULT_MAX_FPS = 30
EVENT_REMOTE_KEY = "homekit_plus_tv_remote_key_pressed"

HVAC_MODE_OPTIONS = ["off", "heat", "cool", "auto"]
ALARM_MODE_OPTIONS = ["stay", "away", "night"]

BINARY_TYPES = [
    TYPE_MOTION,
    TYPE_OCCUPANCY,
    TYPE_CONTACT,
    TYPE_LEAK,
    TYPE_SMOKE,
    TYPE_CARBON_MONOXIDE,
]
ON_OFF_TYPES = [
    TYPE_SWITCH,
    TYPE_OUTLET,
    TYPE_LIGHTBULB,
    TYPE_FAN,
    TYPE_VALVE,
    TYPE_SPRINKLER,
    TYPE_SHOWER,
    TYPE_FAUCET,
]

# Which accessory types are allowed for each Home Assistant domain. The first
# entry is the fallback default (see entity_types.default_type for smarter
# device-class based defaults).
DOMAIN_TYPES: dict[str, list[str]] = {
    "light": [TYPE_LIGHTBULB, TYPE_SWITCH, TYPE_OUTLET, TYPE_FAN],
    "switch": [*ON_OFF_TYPES, *BINARY_TYPES],
    "input_boolean": [*ON_OFF_TYPES, *BINARY_TYPES],
    "fan": [TYPE_FAN, TYPE_SWITCH, TYPE_OUTLET, TYPE_LIGHTBULB],
    "cover": [
        TYPE_WINDOW_COVERING,
        TYPE_GARAGE_DOOR,
        TYPE_DOOR,
        TYPE_WINDOW,
        TYPE_SWITCH,
    ],
    "valve": [TYPE_VALVE, TYPE_SPRINKLER, TYPE_SHOWER, TYPE_FAUCET, TYPE_SWITCH],
    "lock": [TYPE_LOCK, TYPE_SWITCH],
    "climate": [TYPE_THERMOSTAT, TYPE_SWITCH],
    "alarm_control_panel": [TYPE_SECURITY_SYSTEM],
    "sensor": [
        TYPE_TEMPERATURE,
        TYPE_HUMIDITY,
        TYPE_LIGHT_SENSOR,
        TYPE_CO2,
        TYPE_PM25,
        TYPE_PM10,
        TYPE_AQI,
    ],
    "binary_sensor": [*BINARY_TYPES],
    "person": [TYPE_OCCUPANCY, TYPE_MOTION, TYPE_CONTACT],
    "device_tracker": [TYPE_OCCUPANCY, TYPE_MOTION, TYPE_CONTACT],
    "media_player": [TYPE_SWITCH, TYPE_OUTLET, TYPE_TELEVISION, TYPE_RECEIVER],
    "vacuum": [TYPE_SWITCH, TYPE_FAN],
    "humidifier": [TYPE_HUMIDIFIER, TYPE_SWITCH, TYPE_FAN],
    "water_heater": [TYPE_WATER_HEATER, TYPE_SWITCH],
    "camera": [TYPE_CAMERA],
    "siren": [TYPE_SWITCH],
    "remote": [TYPE_SWITCH],
    "automation": [TYPE_SWITCH],
    # Stateless domains: exposed as a switch that resets itself after a press.
    "script": [TYPE_SWITCH, TYPE_OUTLET, TYPE_LIGHTBULB],
    "scene": [TYPE_SWITCH, TYPE_OUTLET, TYPE_LIGHTBULB],
    "button": [TYPE_SWITCH, TYPE_OUTLET],
    "input_button": [TYPE_SWITCH, TYPE_OUTLET],
}

SUPPORTED_DOMAINS = list(DOMAIN_TYPES)
MOMENTARY_DOMAINS = {"script", "scene", "button", "input_button"}

DEFAULT_LOW_BATTERY_THRESHOLD = 20
DEFAULT_CO2_THRESHOLD = 1000

PAIRING_NOTIFICATION_ID = f"{DOMAIN}_pairing_{{}}"
QR_VIEW_URL = f"/api/{DOMAIN}/pairingqr"

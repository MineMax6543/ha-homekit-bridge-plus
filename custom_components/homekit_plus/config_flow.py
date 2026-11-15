"""Config and options flow for HomeKit Bridge Plus.

Options are edited in a menu: every sub step returns to the menu and nothing
is applied until "Save and apply" is chosen.
"""

from __future__ import annotations

import copy
import socket
from typing import Any
import uuid

from pyhap.util import generate_pincode
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.selector import (
    AreaSelector,
    AreaSelectorConfig,
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    LabelSelector,
    LabelSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    ALARM_MODE_OPTIONS,
    BINARY_TYPES,
    CONF_ADVERTISE_IP,
    CONF_ALARM_MODES,
    CONF_CO2_THRESHOLD,
    CONF_CODE,
    CONF_ENTITIES,
    CONF_ENTITY_CONFIG,
    CONF_EXCLUDE_ENTITIES,
    CONF_FEATURES,
    CONF_GROUP_ENTITIES,
    CONF_GROUP_ID,
    CONF_GROUP_NAME,
    CONF_GROUPS,
    CONF_HVAC_MODES,
    CONF_INCLUDE_AREAS,
    CONF_INCLUDE_DOMAINS,
    CONF_INCLUDE_LABELS,
    CONF_INVERT,
    CONF_LINKED_BATTERY,
    CONF_LINKED_HUMIDITY,
    CONF_LINKED_DOORBELL,
    CONF_LINKED_MOTION,
    CONF_LOW_BATTERY_THRESHOLD,
    CONF_MAX_FPS,
    CONF_MAX_HEIGHT,
    CONF_MAX_WIDTH,
    CONF_MODE,
    CONF_NAME,
    CONF_PIN,
    CONF_PORT,
    CONF_SOURCES,
    CONF_STREAM_SOURCE,
    CONF_SUPPORT_AUDIO,
    CONF_TYPE,
    CONF_VIDEO_CODEC,
    DEFAULT_CO2_THRESHOLD,
    DEFAULT_LOW_BATTERY_THRESHOLD,
    DEFAULT_MAX_FPS,
    DEFAULT_MAX_HEIGHT,
    DEFAULT_MAX_WIDTH,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    FEATURE_HUMIDITY,
    FEATURE_TARGET_HUMIDITY,
    FEATURE_LABELS,
    FEATURE_OUTLET_IN_USE,
    FEATURE_POSITION,
    FEATURE_TEMP_RANGE,
    FEATURE_TILT,
    HVAC_MODE_OPTIONS,
    MODE_ACCESSORY,
    MODE_BRIDGE,
    SUPPORTED_DOMAINS,
    TYPE_CAMERA,
    TYPE_CO2,
    TYPE_FEATURES,
    TYPE_HUMIDIFIER,
    TYPE_LABELS,
    TYPE_LOCK,
    TYPE_OUTLET,
    TYPE_RECEIVER,
    TYPE_SECURITY_SYSTEM,
    TYPE_TELEVISION,
    TYPE_TEMPERATURE,
    TYPE_THERMOSTAT,
    TYPE_WINDOW_COVERING,
    VIDEO_CODECS,
)
from .handlers.fan import _supported as fan_supported
from .handlers.light import _supported as light_supported
from .handlers.media import supported_tv_features
from .selection import resolve_exposed
from .util import allowed_types, resolve_features, resolve_type

NEW_GROUP = "__new__"

HVAC_LABELS = {"off": "Off", "heat": "Heat", "cool": "Cool", "auto": "Auto (heat/cool)"}
ALARM_LABELS = {"stay": "Home / Stay", "away": "Away", "night": "Night"}


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _used_ports(hass: HomeAssistant, exclude_entry: str | None = None) -> set[int]:
    return {
        int({**e.data, **e.options}.get(CONF_PORT, 0))
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != exclude_entry
    }


def _options(values: dict[str, str]) -> list[SelectOptionDict]:
    return [SelectOptionDict(value=k, label=v) for k, v in values.items()]


def supported_features(state: State | None, acc_type: str) -> list[str]:
    """Features of a type that this particular entity can actually do."""
    available = TYPE_FEATURES.get(acc_type, [])
    if state is None:
        return list(available)
    flags = int(state.attributes.get("supported_features") or 0)
    if acc_type == "lightbulb":
        supported = light_supported(state)
    elif acc_type == "fan":
        supported = fan_supported(state)
    elif state.domain == "cover":
        supported = set()
        if flags & 4:
            supported.add(FEATURE_POSITION)
        if flags & 128 and acc_type == TYPE_WINDOW_COVERING:
            supported.add(FEATURE_TILT)
    elif acc_type == TYPE_THERMOSTAT:
        supported = set()
        if "current_humidity" in state.attributes:
            supported.add(FEATURE_HUMIDITY)
        if flags & 2:
            supported.add(FEATURE_TEMP_RANGE)
    elif acc_type == TYPE_OUTLET:
        supported = {FEATURE_OUTLET_IN_USE}
    elif acc_type in (TYPE_TELEVISION, TYPE_RECEIVER):
        supported = supported_tv_features(state)
    elif acc_type == TYPE_HUMIDIFIER:
        supported = {FEATURE_TARGET_HUMIDITY}
    else:
        supported = set()
    return [f for f in available if f in supported]


def _suggest(value: Any) -> dict[str, Any]:
    return {"suggested_value": value}


class HomeKitPlusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a bridge."""

    VERSION = 1

    def __init__(self) -> None:
        self._mode = MODE_BRIDGE

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose bridge or accessory mode."""
        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            if self._mode == MODE_ACCESSORY:
                return await self.async_step_accessory()
            return await self.async_step_bridge()
        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=MODE_BRIDGE): SelectSelector(
                    SelectSelectorConfig(
                        options=_options(
                            {
                                MODE_BRIDGE: "Bridge: many entities, paired once",
                                MODE_ACCESSORY: (
                                    "Accessory: one entity paired on its own "
                                    "(needed for TVs, best for cameras)"
                                ),
                            }
                        ),
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    def _default_port(self) -> int:
        used = _used_ports(self.hass)
        port = DEFAULT_PORT
        while port in used:
            port += 1
        return port

    async def _validate_port(self, port: int) -> str | None:
        if port in _used_ports(self.hass):
            return "port_used"
        if not await self.hass.async_add_executor_job(_port_free, port):
            return "port_in_use"
        return None

    def _create(self, name: str, port: int, entities: list[str]) -> ConfigFlowResult:
        return self.async_create_entry(
            title=name,
            data={
                CONF_NAME: name,
                CONF_PORT: port,
                CONF_PIN: generate_pincode().decode(),
                CONF_MODE: self._mode,
            },
            options={CONF_ENTITIES: entities, CONF_ENTITY_CONFIG: {}, CONF_GROUPS: []},
        )

    async def async_step_bridge(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Bridge mode: name, port, first entities."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = int(user_input[CONF_PORT])
            if error := await self._validate_port(port):
                errors[CONF_PORT] = error
            else:
                return self._create(
                    user_input[CONF_NAME], port, user_input.get(CONF_ENTITIES, [])
                )
        count = len(self.hass.config_entries.async_entries(DOMAIN))
        default_name = DEFAULT_NAME if count == 0 else f"{DEFAULT_NAME} {count + 1}"
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=default_name): str,
                vol.Required(CONF_PORT, default=self._default_port()): vol.All(
                    vol.Coerce(int), vol.Range(min=1024, max=65535)
                ),
                vol.Optional(CONF_ENTITIES, default=[]): EntitySelector(
                    EntitySelectorConfig(domain=SUPPORTED_DOMAINS, multiple=True)
                ),
            }
        )
        return self.async_show_form(
            step_id="bridge",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_accessory(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Accessory mode: one entity."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = int(user_input[CONF_PORT])
            entity_id = user_input[CONF_ENTITIES]
            if error := await self._validate_port(port):
                errors[CONF_PORT] = error
            elif self.hass.states.get(entity_id) is None:
                errors[CONF_ENTITIES] = "entity_missing"
            else:
                state = self.hass.states.get(entity_id)
                name = (user_input.get(CONF_NAME) or "").strip() or state.name
                return self._create(name, port, [entity_id])
        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITIES): EntitySelector(
                    EntitySelectorConfig(domain=SUPPORTED_DOMAINS)
                ),
                vol.Optional(CONF_NAME): str,
                vol.Required(CONF_PORT, default=self._default_port()): vol.All(
                    vol.Coerce(int), vol.Range(min=1024, max=65535)
                ),
            }
        )
        return self.async_show_form(
            step_id="accessory",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HomeKitPlusOptionsFlow()


class HomeKitPlusOptionsFlow(OptionsFlow):
    """Menu driven options."""

    def __init__(self) -> None:
        self._opts: dict[str, Any] | None = None
        self._entity: str | None = None
        self._group_id: str | None = None

    @property
    def opts(self) -> dict[str, Any]:
        if self._opts is None:
            self._opts = copy.deepcopy(dict(self.config_entry.options))
            self._opts.setdefault(CONF_ENTITY_CONFIG, {})
            self._opts.setdefault(CONF_GROUPS, [])
        return self._opts

    @property
    def accessory_mode(self) -> bool:
        return self.config_entry.data.get(CONF_MODE) == MODE_ACCESSORY

    def _exposed(self) -> list[str]:
        exposed = resolve_exposed(self.hass, self.opts)
        return exposed[:1] if self.accessory_mode else exposed

    # ---- menu ------------------------------------------------------------
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        bridge = getattr(self.config_entry, "runtime_data", None)
        skipped = getattr(bridge, "skipped", {}) or {}
        skipped_text = (
            "\n".join(f"- `{eid}`: {why}" for eid, why in sorted(skipped.items()))
            if skipped
            else "none"
        )
        if self.accessory_mode:
            menu = ["select_entities", "configure_entity", "bridge"]
        else:
            menu = [
                "select_entities",
                "filters",
                "configure_entity",
                "groups",
                "bridge",
            ]
        return self.async_show_menu(
            step_id="init",
            menu_options=menu,
            description_placeholders={
                "count": str(len(self._exposed())),
                "groups": str(len(self.opts[CONF_GROUPS])),
                "skipped": skipped_text,
            },
        )

    def _async_apply(self) -> ConfigFlowResult:
        """Save right away; the bridge reloads with the new options."""
        # Drop config of entities that are no longer exposed
        exposed = set(self._exposed())
        self.opts[CONF_ENTITY_CONFIG] = {
            eid: cfg for eid, cfg in self.opts[CONF_ENTITY_CONFIG].items() if eid in exposed
        }
        return self.async_create_entry(data=self.opts)

    # ---- which entities ----------------------------------------------------
    async def async_step_select_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self.accessory_mode:
            if user_input is not None:
                self.opts[CONF_ENTITIES] = [user_input[CONF_ENTITIES]]
                return self._async_apply()
            current = (self.opts.get(CONF_ENTITIES) or [None])[0]
            schema = vol.Schema(
                {
                    vol.Required(CONF_ENTITIES, description=_suggest(current)): EntitySelector(
                        EntitySelectorConfig(domain=SUPPORTED_DOMAINS)
                    ),
                }
            )
            return self.async_show_form(
                step_id="select_entities",
                data_schema=schema,
                description_placeholders={"indirect": ""},
            )

        if user_input is not None:
            self.opts[CONF_ENTITIES] = user_input.get(CONF_ENTITIES, [])
            return self._async_apply()
        explicit = set(self.opts.get(CONF_ENTITIES) or [])
        indirect = [eid for eid in self._exposed() if eid not in explicit]
        indirect_text = (
            "\n\nAlso exposed through labels, areas, domains or combined accessories "
            "(removing them here has no effect, add them to **Exclude** under "
            "*Include by label / area / domain* instead):\n"
            + "\n".join(f"- `{eid}`" for eid in indirect)
            if indirect
            else ""
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENTITIES, description=_suggest(self.opts.get(CONF_ENTITIES, []))
                ): EntitySelector(EntitySelectorConfig(domain=SUPPORTED_DOMAINS, multiple=True)),
            }
        )
        return self.async_show_form(
            step_id="select_entities",
            data_schema=schema,
            description_placeholders={"indirect": indirect_text},
        )

    async def async_step_filters(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            for key in (
                CONF_INCLUDE_LABELS,
                CONF_INCLUDE_AREAS,
                CONF_INCLUDE_DOMAINS,
                CONF_EXCLUDE_ENTITIES,
            ):
                self.opts[key] = user_input.get(key, [])
            return self._async_apply()
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INCLUDE_LABELS, description=_suggest(self.opts.get(CONF_INCLUDE_LABELS, []))
                ): LabelSelector(LabelSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_INCLUDE_AREAS, description=_suggest(self.opts.get(CONF_INCLUDE_AREAS, []))
                ): AreaSelector(AreaSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_INCLUDE_DOMAINS,
                    description=_suggest(self.opts.get(CONF_INCLUDE_DOMAINS, [])),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=sorted(SUPPORTED_DOMAINS),
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_EXCLUDE_ENTITIES,
                    description=_suggest(self.opts.get(CONF_EXCLUDE_ENTITIES, [])),
                ): EntitySelector(EntitySelectorConfig(domain=SUPPORTED_DOMAINS, multiple=True)),
            }
        )
        return self.async_show_form(step_id="filters", data_schema=schema)

    # ---- per entity configuration -----------------------------------------
    async def async_step_configure_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        exposed = self._exposed()
        if self.accessory_mode and exposed:
            self._entity = exposed[0]
            return await self.async_step_entity_type()
        if user_input is not None:
            if not exposed:
                return await self.async_step_init()
            self._entity = user_input["entity"]
            return await self.async_step_entity_type()

        if not exposed:
            return self.async_show_form(
                step_id="configure_entity",
                data_schema=vol.Schema({}),
                errors={"base": "no_entities"},
            )
        options = []
        for eid in exposed:
            state = self.hass.states.get(eid)
            cfg = self.opts[CONF_ENTITY_CONFIG].get(eid, {})
            acc_type = resolve_type(eid, state, cfg, self.accessory_mode)
            name = cfg.get(CONF_NAME) or (state.name if state else eid)
            type_label = TYPE_LABELS.get(acc_type, "⚠ needs a type") if acc_type else "⚠ needs a type"
            marker = " ✎" if cfg else ""
            options.append(
                SelectOptionDict(value=eid, label=f"{name} ({eid}) → {type_label}{marker}")
            )
        schema = vol.Schema(
            {
                vol.Required("entity"): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="configure_entity", data_schema=schema)

    async def async_step_entity_type(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        eid = self._entity
        assert eid is not None
        state = self.hass.states.get(eid)
        configs = self.opts[CONF_ENTITY_CONFIG]
        cfg = dict(configs.get(eid, {}))

        if user_input is not None:
            if user_input.get("reset"):
                configs.pop(eid, None)
                return self._async_apply()
            new_type = user_input.get(CONF_TYPE)
            if new_type != resolve_type(eid, state, cfg, self.accessory_mode):
                # Type changed -> type specific options no longer apply
                for key in (
                    CONF_FEATURES,
                    CONF_HVAC_MODES,
                    CONF_ALARM_MODES,
                    CONF_INVERT,
                    CONF_SOURCES,
                ):
                    cfg.pop(key, None)
            cfg[CONF_TYPE] = new_type
            if name := (user_input.get(CONF_NAME) or "").strip():
                cfg[CONF_NAME] = name
            else:
                cfg.pop(CONF_NAME, None)
            configs[eid] = cfg
            return await self.async_step_entity_options()

        allowed = allowed_types(eid, self.accessory_mode)
        current = resolve_type(eid, state, cfg, self.accessory_mode)
        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, description=_suggest(cfg.get(CONF_NAME))): TextSelector(),
                vol.Required(CONF_TYPE, default=current or allowed[0]): SelectSelector(
                    SelectSelectorConfig(
                        options=_options({t: TYPE_LABELS[t] for t in allowed}),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("reset", default=False): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="entity_type",
            data_schema=schema,
            description_placeholders={
                "entity_id": eid,
                "name": state.name if state else eid,
            },
        )

    async def async_step_entity_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        eid = self._entity
        assert eid is not None
        state = self.hass.states.get(eid)
        cfg = self.opts[CONF_ENTITY_CONFIG].setdefault(eid, {})
        acc_type = resolve_type(eid, state, cfg, self.accessory_mode)
        assert acc_type is not None
        feature_choices = supported_features(state, acc_type)

        if user_input is not None:
            keys = (
                CONF_FEATURES,
                CONF_HVAC_MODES,
                CONF_ALARM_MODES,
                CONF_CODE,
                CONF_INVERT,
                CONF_CO2_THRESHOLD,
                CONF_LINKED_BATTERY,
                CONF_LOW_BATTERY_THRESHOLD,
                CONF_LINKED_HUMIDITY,
                CONF_LINKED_MOTION,
                CONF_LINKED_DOORBELL,
                CONF_SOURCES,
                CONF_STREAM_SOURCE,
                CONF_VIDEO_CODEC,
                CONF_SUPPORT_AUDIO,
                CONF_MAX_WIDTH,
                CONF_MAX_HEIGHT,
                CONF_MAX_FPS,
            )
            for key in keys:
                value = user_input.get(key)
                if value in (None, ""):
                    cfg.pop(key, None)
                else:
                    cfg[key] = value
            if CONF_FEATURES in user_input:
                cfg[CONF_FEATURES] = user_input[CONF_FEATURES]  # [] is meaningful
            return self._async_apply()

        fields: dict[Any, Any] = {}
        if feature_choices:
            enabled = [f for f in resolve_features(acc_type, cfg) if f in feature_choices]
            fields[vol.Optional(CONF_FEATURES, default=enabled)] = SelectSelector(
                SelectSelectorConfig(
                    options=_options({f: FEATURE_LABELS[f] for f in feature_choices}),
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        if acc_type == TYPE_THERMOSTAT:
            fields[
                vol.Optional(CONF_HVAC_MODES, default=cfg.get(CONF_HVAC_MODES, HVAC_MODE_OPTIONS))
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=_options(HVAC_LABELS), multiple=True, mode=SelectSelectorMode.LIST
                )
            )
        if acc_type == TYPE_SECURITY_SYSTEM:
            fields[
                vol.Optional(
                    CONF_ALARM_MODES, default=cfg.get(CONF_ALARM_MODES, ALARM_MODE_OPTIONS)
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=_options(ALARM_LABELS), multiple=True, mode=SelectSelectorMode.LIST
                )
            )
        if acc_type in (TYPE_SECURITY_SYSTEM, TYPE_LOCK):
            fields[vol.Optional(CONF_CODE, description=_suggest(cfg.get(CONF_CODE)))] = (
                TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
            )
        if acc_type in BINARY_TYPES:
            fields[vol.Optional(CONF_INVERT, default=bool(cfg.get(CONF_INVERT)))] = (
                BooleanSelector()
            )
        if acc_type == TYPE_CO2:
            fields[
                vol.Optional(
                    CONF_CO2_THRESHOLD, default=cfg.get(CONF_CO2_THRESHOLD, DEFAULT_CO2_THRESHOLD)
                )
            ] = NumberSelector(
                NumberSelectorConfig(
                    min=400, max=5000, step=50, unit_of_measurement="ppm",
                    mode=NumberSelectorMode.BOX,
                )
            )
        if acc_type in (TYPE_TELEVISION, TYPE_RECEIVER) and state is not None:
            source_list = list(state.attributes.get("source_list") or [])
            if source_list:
                fields[
                    vol.Optional(CONF_SOURCES, default=cfg.get(CONF_SOURCES) or source_list)
                ] = SelectSelector(
                    SelectSelectorConfig(
                        options=source_list, multiple=True, mode=SelectSelectorMode.LIST
                    )
                )
        if acc_type == TYPE_CAMERA:
            fields.update(self._camera_fields(cfg))
        if acc_type in (TYPE_TEMPERATURE, TYPE_THERMOSTAT, TYPE_HUMIDIFIER):
            fields[
                vol.Optional(CONF_LINKED_HUMIDITY, description=_suggest(cfg.get(CONF_LINKED_HUMIDITY)))
            ] = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="humidity"))
        fields[
            vol.Optional(CONF_LINKED_BATTERY, description=_suggest(cfg.get(CONF_LINKED_BATTERY)))
        ] = EntitySelector(
            EntitySelectorConfig(
                filter=[
                    {"domain": "sensor", "device_class": "battery"},
                    {"domain": "binary_sensor", "device_class": "battery"},
                ]
            )
        )
        fields[
            vol.Optional(
                CONF_LOW_BATTERY_THRESHOLD,
                default=cfg.get(CONF_LOW_BATTERY_THRESHOLD, DEFAULT_LOW_BATTERY_THRESHOLD),
            )
        ] = NumberSelector(
            NumberSelectorConfig(
                min=1, max=99, step=1, unit_of_measurement="%", mode=NumberSelectorMode.SLIDER
            )
        )
        return self.async_show_form(
            step_id="entity_options",
            data_schema=vol.Schema(fields),
            description_placeholders={
                "entity_id": eid,
                "type": TYPE_LABELS.get(acc_type, acc_type),
            },
        )

    @staticmethod
    def _camera_fields(cfg: dict[str, Any]) -> dict[Any, Any]:
        def number(key: str, default: int, low: int, high: int, step: int, unit: str):
            return {
                vol.Optional(key, default=cfg.get(key, default)): NumberSelector(
                    NumberSelectorConfig(
                        min=low,
                        max=high,
                        step=step,
                        unit_of_measurement=unit,
                        mode=NumberSelectorMode.BOX,
                    )
                )
            }

        return {
            vol.Optional(
                CONF_STREAM_SOURCE, description=_suggest(cfg.get(CONF_STREAM_SOURCE))
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Optional(
                CONF_VIDEO_CODEC, default=cfg.get(CONF_VIDEO_CODEC, VIDEO_CODECS[0])
            ): SelectSelector(
                SelectSelectorConfig(options=VIDEO_CODECS, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(
                CONF_SUPPORT_AUDIO, default=bool(cfg.get(CONF_SUPPORT_AUDIO))
            ): BooleanSelector(),
            **number(CONF_MAX_WIDTH, DEFAULT_MAX_WIDTH, 320, 1920, 1, "px"),
            **number(CONF_MAX_HEIGHT, DEFAULT_MAX_HEIGHT, 180, 1080, 1, "px"),
            **number(CONF_MAX_FPS, DEFAULT_MAX_FPS, 5, 30, 1, "fps"),
            vol.Optional(
                CONF_LINKED_MOTION, description=_suggest(cfg.get(CONF_LINKED_MOTION))
            ): EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
            vol.Optional(
                CONF_LINKED_DOORBELL, description=_suggest(cfg.get(CONF_LINKED_DOORBELL))
            ): EntitySelector(EntitySelectorConfig(domain=["binary_sensor", "event"])),
        }

    # ---- combined accessories ---------------------------------------------
    async def async_step_groups(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            choice = user_input["group"]
            self._group_id = None if choice == NEW_GROUP else choice
            return await self.async_step_group_edit()
        options = [SelectOptionDict(value=NEW_GROUP, label="➕ New combined accessory")]
        options += [
            SelectOptionDict(
                value=g[CONF_GROUP_ID],
                label=f"{g[CONF_GROUP_NAME]} ({len(g[CONF_GROUP_ENTITIES])} entities)",
            )
            for g in self.opts[CONF_GROUPS]
        ]
        schema = vol.Schema(
            {
                vol.Required("group", default=NEW_GROUP): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                )
            }
        )
        return self.async_show_form(step_id="groups", data_schema=schema)

    async def async_step_group_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        groups: list[dict[str, Any]] = self.opts[CONF_GROUPS]
        group = next((g for g in groups if g[CONF_GROUP_ID] == self._group_id), None)
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get("delete") and group is not None:
                groups.remove(group)
                return self._async_apply()
            entities = user_input.get(CONF_GROUP_ENTITIES, [])
            others = {
                eid
                for g in groups
                if g is not group
                for eid in g[CONF_GROUP_ENTITIES]
            }
            if not entities:
                errors[CONF_GROUP_ENTITIES] = "group_empty"
            elif others & set(entities):
                errors[CONF_GROUP_ENTITIES] = "entity_in_other_group"
            else:
                if group is None:
                    group = {CONF_GROUP_ID: uuid.uuid4().hex[:8]}
                    groups.append(group)
                group[CONF_GROUP_NAME] = user_input[CONF_GROUP_NAME].strip()
                group[CONF_GROUP_ENTITIES] = entities
                return self._async_apply()

        current = user_input or group or {}
        fields: dict[Any, Any] = {
            vol.Required(CONF_GROUP_NAME, description=_suggest(current.get(CONF_GROUP_NAME))): (
                TextSelector()
            ),
            vol.Required(
                CONF_GROUP_ENTITIES, description=_suggest(current.get(CONF_GROUP_ENTITIES, []))
            ): EntitySelector(EntitySelectorConfig(domain=SUPPORTED_DOMAINS, multiple=True)),
        }
        if group is not None:
            fields[vol.Optional("delete", default=False)] = BooleanSelector()
        return self.async_show_form(
            step_id="group_edit", data_schema=vol.Schema(fields), errors=errors
        )

    # ---- bridge settings ----------------------------------------------------
    async def async_step_bridge(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.config_entry
        current = {**entry.data, **self.opts}
        if user_input is not None:
            port = int(user_input[CONF_PORT])
            if port != int(current.get(CONF_PORT, DEFAULT_PORT)):
                if port in _used_ports(self.hass, entry.entry_id):
                    errors[CONF_PORT] = "port_used"
                elif not await self.hass.async_add_executor_job(_port_free, port):
                    errors[CONF_PORT] = "port_in_use"
            if not errors:
                self.opts[CONF_NAME] = user_input[CONF_NAME]
                self.opts[CONF_PORT] = port
                self.opts[CONF_ADVERTISE_IP] = (user_input.get(CONF_ADVERTISE_IP) or "").strip()
                return self._async_apply()
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=current.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Required(CONF_PORT, default=int(current.get(CONF_PORT, DEFAULT_PORT))): vol.All(
                    vol.Coerce(int), vol.Range(min=1024, max=65535)
                ),
                vol.Optional(
                    CONF_ADVERTISE_IP, description=_suggest(current.get(CONF_ADVERTISE_IP))
                ): str,
            }
        )
        return self.async_show_form(
            step_id="bridge",
            data_schema=schema,
            errors=errors,
            description_placeholders={"pin": entry.data.get(CONF_PIN, "?")},
        )

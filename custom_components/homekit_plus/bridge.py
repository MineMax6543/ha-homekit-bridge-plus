"""The HomeKit bridge: HAP driver, accessories and state synchronisation."""

from __future__ import annotations

from collections import defaultdict
import io
import logging
import os
import secrets
from typing import Any

from pyhap.accessory import Accessory, Bridge
from pyhap.accessory_driver import AccessoryDriver
from pyhap.const import (
    CATEGORY_CAMERA,
    CATEGORY_OTHER,
    CATEGORY_VIDEO_DOOR_BELL,
    STANDALONE_AID,
)
import pyqrcode

from homeassistant.components import network, persistent_notification, zeroconf
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .accessory import HAAccessory, HACameraAccessory
from .const import (
    CONF_ADVERTISE_IP,
    CONF_ENTITY_CONFIG,
    CONF_GROUP_ENTITIES,
    CONF_GROUP_ID,
    CONF_GROUP_NAME,
    CONF_GROUPS,
    CONF_LINKED_BATTERY,
    CONF_LINKED_DOORBELL,
    CONF_LINKED_HUMIDITY,
    CONF_LINKED_MOTION,
    CONF_MODE,
    CONF_NAME,
    CONF_PIN,
    CONF_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    MANUFACTURER,
    MAX_BRIDGED_ACCESSORIES,
    MODE_ACCESSORY,
    MODEL,
    PAIRING_NOTIFICATION_ID,
    QR_VIEW_URL,
    TYPE_CAMERA,
    TYPE_MOTION,
)
from .handlers import (
    HANDLERS,
    BatteryHandler,
    BinaryHandler,
    CharFeedHandler,
    DoorbellHandler,
    Handler,
    HumidityHandler,
)
from .selection import has_filters, resolve_exposed
from .util import cleanup_name, resolve_type

_LOGGER = logging.getLogger(__name__)

VERSION = "0.2.1"


class BridgeNotReady(Exception):
    """The configured accessory can't be built (yet)."""


def get_settings(entry: ConfigEntry) -> dict[str, Any]:
    """Bridge settings: options override the initial data."""
    return {**entry.data, **entry.options}


class HomeDriver(AccessoryDriver):
    """AccessoryDriver that keeps the pairing notification in sync."""

    def __init__(self, bridge: HomeKitBridgePlus, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._bridge = bridge

    def pair(self, *args: Any, **kwargs: Any) -> bool:
        success = super().pair(*args, **kwargs)
        if success:
            self._bridge.async_dismiss_pairing()
        return success

    def unpair(self, client_uuid: Any) -> None:
        super().unpair(client_uuid)
        if not self.state.paired:
            self._bridge.async_show_pairing()


class HomeKitBridgePlus:
    """One HomeKit bridge for one config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        settings = get_settings(entry)
        self.name = cleanup_name(settings.get(CONF_NAME) or DEFAULT_NAME, DEFAULT_NAME)
        self.port = int(settings.get(CONF_PORT) or DEFAULT_PORT)
        self.advertise_ip = settings.get(CONF_ADVERTISE_IP) or None
        self.accessory_mode = settings.get(CONF_MODE) == MODE_ACCESSORY
        self.options = dict(entry.options)
        self.driver: HomeDriver | None = None
        self.bridge: Bridge | None = None  # bridge mode only
        self.root: Accessory | None = None  # what is paired: bridge or accessory
        self.address: str = "0.0.0.0"
        self.handlers_by_entity: dict[str, list[Handler]] = defaultdict(list)
        self.exposed: list[str] = []
        self.skipped: dict[str, str] = {}
        self._unsubs: list[CALLBACK_TYPE] = []
        self._aid_store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.aids")
        self._aids: dict[str, int] = {}
        self._qr_secret = secrets.token_hex(16)
        self.qr_svg: bytes | None = None
        self.running = False

    # ------------------------------------------------------------------
    @property
    def persist_file(self) -> str:
        return self.hass.config.path(".storage", f"{DOMAIN}.{self.entry.entry_id}.state")

    @property
    def notification_id(self) -> str:
        return PAIRING_NOTIFICATION_ID.format(self.entry.entry_id)

    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        """Create the driver and load persisted pairing state."""
        self._aids = (await self._aid_store.async_load()) or {}
        self.address = self.advertise_ip or await network.async_get_source_ip(self.hass)
        zc = await zeroconf.async_get_async_instance(self.hass)
        self.driver = HomeDriver(
            self,
            loop=self.hass.loop,
            address=self.address,
            listen_address="0.0.0.0",
            advertised_address=self.address,
            port=self.port,
            pincode=(self.entry.data.get(CONF_PIN) or "").encode() or None,
            persist_file=self.persist_file,
            async_zeroconf_instance=zc,
            zeroconf_server=f"homekit-plus-{self.entry.entry_id.lower()}.local.",
        )
        if await self.hass.async_add_executor_job(os.path.exists, self.persist_file):
            await self.hass.async_add_executor_job(self.driver.load)

    async def async_start(self) -> None:
        """Build accessories and start advertising."""
        assert self.driver is not None
        if self.accessory_mode:
            self.root = self._build_standalone()
        else:
            self.bridge = Bridge(self.driver, self.name)
            self.bridge.set_info_service(
                firmware_revision=VERSION,
                manufacturer=MANUFACTURER,
                model=MODEL,
                serial_number=self.entry.entry_id,
            )
            self._build_accessories()
            await self._aid_store.async_save(self._aids)
            self.root = self.bridge
        self.driver.add_accessory(self.root)

        # Initial state push, then follow changes
        for entity_id, handlers in self.handlers_by_entity.items():
            if state := self.hass.states.get(entity_id):
                for handler in handlers:
                    self._safe_update(handler, state)
        if self.handlers_by_entity:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, list(self.handlers_by_entity), self._async_state_changed
                )
            )
        if has_filters(self.options) and not self.accessory_mode:
            self._watch_registries()

        await self.driver.async_start()
        self.running = True
        if not self.driver.state.paired:
            self.async_show_pairing()
        _LOGGER.info(
            "HomeKit Bridge Plus '%s' started on port %s (%s)",
            self.name,
            self.port,
            "accessory mode"
            if self.bridge is None
            else f"{len(self.bridge.accessories)} accessories",
        )

    async def async_stop(self) -> None:
        """Stop the driver."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self.driver and self.running:
            self.running = False
            await self.driver.async_stop()

    # ------------------------------------------------------------------
    def _aid_for(self, key: str) -> int:
        """Stable accessory ids; never reused once handed out."""
        if key not in self._aids:
            used = set(self._aids.values())
            aid = max([*used, 1]) + 1
            if aid == 7:  # HAP-python avoids AID 7 (see pyhap issue #61)
                aid = 8
            self._aids[key] = aid
        return self._aids[key]

    def _entity_cfg(self, entity_id: str) -> dict[str, Any]:
        return dict((self.options.get(CONF_ENTITY_CONFIG) or {}).get(entity_id) or {})

    def _build_standalone(self) -> Accessory:
        """Accessory mode: exactly one entity, paired on its own."""
        self.exposed = resolve_exposed(self.hass, self.options)[:1]
        if not self.exposed:
            raise BridgeNotReady("No entity selected for this accessory")
        entity_id = self.exposed[0]
        acc = self._build_unit(f"entity:{entity_id}", None, [entity_id], STANDALONE_AID)
        if acc is None:
            raise BridgeNotReady(
                f"{entity_id}: {self.skipped.get(entity_id, 'cannot be exposed')}"
            )
        return acc

    def _build_accessories(self) -> None:
        assert self.bridge is not None
        self.exposed = resolve_exposed(self.hass, self.options)
        exposed_set = set(self.exposed)
        grouped: set[str] = set()
        units: list[tuple[str, str | None, list[str]]] = []  # (key, group name, entities)

        for group in self.options.get(CONF_GROUPS) or []:
            members = [e for e in group.get(CONF_GROUP_ENTITIES) or [] if e in exposed_set]
            if not members:
                continue
            grouped.update(members)
            units.append((f"group:{group[CONF_GROUP_ID]}", group.get(CONF_GROUP_NAME), members))
        for entity_id in self.exposed:
            if entity_id not in grouped:
                units.append((f"entity:{entity_id}", None, [entity_id]))

        if len(units) > MAX_BRIDGED_ACCESSORIES:
            _LOGGER.warning(
                "%s: %d accessories selected but a HomeKit bridge supports at most %d; "
                "the rest are ignored. Create a second bridge for them",
                self.name,
                len(units),
                MAX_BRIDGED_ACCESSORIES,
            )
            for _key, _, members in units[MAX_BRIDGED_ACCESSORIES:]:
                for eid in members:
                    self.skipped[eid] = "bridge limit (150) reached"
            units = units[:MAX_BRIDGED_ACCESSORIES]

        for key, group_name, members in units:
            try:
                acc = self._build_unit(key, group_name, members, self._aid_for(key))
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Failed to create HomeKit accessory for %s", members)
                continue
            if acc is not None:
                self.bridge.add_accessory(acc)

    def _build_unit(
        self, key: str, group_name: str | None, members: list[str], aid: int
    ) -> Accessory | None:
        valid: list[tuple[str, State, str]] = []
        for eid in members:
            state = self.hass.states.get(eid)
            if state is None:
                self.skipped[eid] = "entity has no state (not loaded yet?)"
                _LOGGER.warning("%s: skipping %s, it has no state", self.name, eid)
                continue
            acc_type = resolve_type(eid, state, self._entity_cfg(eid), self.accessory_mode)
            if acc_type is None:
                self.skipped[eid] = "no accessory type; pick one in the options"
                _LOGGER.warning(
                    "%s: skipping %s, can't guess a HomeKit type. Pick one in the "
                    "integration options",
                    self.name,
                    eid,
                )
                continue
            valid.append((eid, state, acc_type))

        # A camera has to be the accessory itself: put it first, max one.
        cameras = [v for v in valid if v[2] == TYPE_CAMERA]
        for extra in cameras[1:]:
            self.skipped[extra[0]] = "only one camera per accessory"
            valid.remove(extra)
        if cameras:
            valid.remove(cameras[0])
            valid.insert(0, cameras[0])
        if not valid:
            return None

        first_eid, first_state, first_type = valid[0]
        first_cfg = self._entity_cfg(first_eid)
        if self.accessory_mode:
            acc_name = self.name
        else:
            acc_name = cleanup_name(
                group_name or first_cfg.get(CONF_NAME) or first_state.name, first_eid
            )
        acc: HAAccessory | HACameraAccessory
        if first_type == TYPE_CAMERA:
            acc = HACameraAccessory(
                self.hass, self.driver, acc_name, aid, first_eid, first_cfg, self.address
            )
        else:
            acc = HAAccessory(self.hass, self.driver, acc_name, aid)
        acc.primary_entities = [eid for eid, _, _ in valid]
        self._set_info(acc, first_eid, is_group=group_name is not None)

        for eid, state, acc_type in valid:
            cfg = self._entity_cfg(eid)
            name = cleanup_name(cfg.get(CONF_NAME) or state.name, eid)
            handler = HANDLERS[acc_type](self.hass, acc, eid, acc_type, cfg, name, state)
            self._register(acc, handler)
            if acc.category == CATEGORY_OTHER and handler.category != CATEGORY_OTHER:
                acc.category = handler.category
            self._add_linked(acc, handler, cfg, name)

        if group_name is not None and first_type != TYPE_CAMERA and len(acc.services) > 1:
            primary = acc.services[1]
            for serv in acc.services:
                serv.is_primary_service = serv is primary
        return acc

    def _linked_state(self, cfg: dict[str, Any], conf_key: str) -> tuple[str, State] | None:
        eid = cfg.get(conf_key)
        if not eid:
            return None
        state = self.hass.states.get(eid)
        if state is None:
            _LOGGER.warning("%s: linked entity %s has no state", self.name, eid)
            return None
        return eid, state

    def _add_linked(
        self, acc: Accessory, primary: Handler, cfg: dict[str, Any], name: str
    ) -> None:
        hass = self.hass
        if linked := self._linked_state(cfg, CONF_LINKED_BATTERY):
            eid, state = linked
            sub_name = cleanup_name(f"{name} Battery")
            self._register(
                acc, BatteryHandler(hass, acc, eid, "battery", cfg, sub_name, state)
            )
        if linked := self._linked_state(cfg, CONF_LINKED_HUMIDITY):
            eid, state = linked
            target_char = getattr(primary, "linked_humidity_char", None)
            handler: Handler
            if target_char is not None:
                handler = CharFeedHandler(
                    hass, acc, eid, "humidity", cfg, name, state, char=target_char
                )
            else:
                sub_name = cleanup_name(f"{name} Humidity")
                handler = HumidityHandler(hass, acc, eid, "humidity", cfg, sub_name, state)
            self._register(acc, handler)
        if linked := self._linked_state(cfg, CONF_LINKED_MOTION):
            eid, state = linked
            sub_name = cleanup_name(f"{name} Motion")
            self._register(
                acc, BinaryHandler(hass, acc, eid, TYPE_MOTION, {}, sub_name, state)
            )
        if linked := self._linked_state(cfg, CONF_LINKED_DOORBELL):
            eid, state = linked
            sub_name = cleanup_name(f"{name} Doorbell")
            self._register(
                acc, DoorbellHandler(hass, acc, eid, "doorbell", cfg, sub_name, state)
            )
            if acc.category == CATEGORY_CAMERA:
                acc.category = CATEGORY_VIDEO_DOOR_BELL

    def _register(self, acc: Accessory, handler: Handler) -> None:
        acc.handlers.append(handler)
        self.handlers_by_entity[handler.entity_id].append(handler)

    def _set_info(self, acc: Accessory, entity_id: str, is_group: bool) -> None:
        manufacturer, model, firmware = MANUFACTURER, "Home Assistant entity", VERSION
        entry = er.async_get(self.hass).async_get(entity_id)
        if entry and entry.device_id:
            device = dr.async_get(self.hass).async_get(entry.device_id)
            if device:
                manufacturer = device.manufacturer or manufacturer
                model = device.model or model
                firmware = device.sw_version or firmware
        if is_group:
            model = "Combined accessory"
        acc.set_info_service(
            firmware_revision=str(firmware)[:64],
            manufacturer=str(manufacturer)[:64],
            model=str(model)[:64],
            serial_number=entity_id[:64],
        )

    # ------------------------------------------------------------------
    @callback
    def _async_state_changed(self, event: Event) -> None:
        new_state: State | None = event.data.get("new_state")
        if new_state is None or new_state.state in ("unavailable", "unknown"):
            return
        for handler in self.handlers_by_entity.get(event.data["entity_id"], []):
            self._safe_update(handler, new_state)

    @staticmethod
    def _safe_update(handler: Handler, state: State) -> None:
        if state.state in ("unavailable", "unknown") and state.domain != "sensor":
            return
        try:
            handler.async_update(state)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Error updating HomeKit state for %s", handler.entity_id)

    # ---- dynamic membership (labels / areas / domains) -----------------
    def _watch_registries(self) -> None:
        debouncer = Debouncer(
            self.hass,
            _LOGGER,
            cooldown=10,
            immediate=False,
            function=self._async_check_membership,
        )

        @callback
        def _changed(_event: Event) -> None:
            debouncer.async_schedule_call()

        self._unsubs.append(
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _changed)
        )
        self._unsubs.append(
            self.hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _changed)
        )
        self._unsubs.append(debouncer.async_shutdown)

    @callback
    def _async_check_membership(self) -> None:
        if resolve_exposed(self.hass, self.options) != self.exposed:
            _LOGGER.info("%s: exposed entities changed, reloading bridge", self.name)
            self.hass.config_entries.async_schedule_reload(self.entry.entry_id)

    # ---- pairing -------------------------------------------------------
    @callback
    def async_show_pairing(self) -> None:
        assert self.driver is not None and self.root is not None
        pin = self.driver.state.pincode.decode()
        buffer = io.BytesIO()
        pyqrcode.create(self.root.xhm_uri()).svg(
            buffer, scale=5, module_color="#000", background="#FFF", quiet_zone=2
        )
        self.qr_svg = buffer.getvalue()
        persistent_notification.async_create(
            self.hass,
            (
                f"To add **{self.name}** to HomeKit, open the Home app, tap "
                f"*Add Accessory* and scan this code or enter **{pin}**.\n\n"
                f"![HomeKit pairing code]({QR_VIEW_URL}?{self.entry.entry_id}-{self._qr_secret})"
            ),
            title=f"HomeKit Bridge Plus pairing: {self.name}",
            notification_id=self.notification_id,
        )

    @callback
    def async_dismiss_pairing(self) -> None:
        self.qr_svg = None
        persistent_notification.async_dismiss(self.hass, self.notification_id)

    def check_qr_secret(self, secret: str) -> bool:
        return secrets.compare_digest(secret, self._qr_secret)

    @callback
    def async_unpair_all(self) -> None:
        """Remove every paired iOS device so the bridge can be paired again."""
        assert self.driver is not None
        for client in list(self.driver.state.paired_clients):
            self.driver.unpair(client)
        self.driver.async_update_advertisement()
        self.async_show_pairing()


@callback
def async_start_when_ready(hass: HomeAssistant, bridge: HomeKitBridgePlus) -> None:
    """Start once HA has started, so every entity has a state."""

    async def _start(_event: Event) -> None:
        bridge._unsubs.remove(unsub)  # noqa: SLF001 - listener fired, drop it
        try:
            await bridge.async_start()
        except OSError as err:
            _LOGGER.error(
                "HomeKit Bridge Plus '%s' could not start on port %s: %s. "
                "Choose another port in the options",
                bridge.name,
                bridge.port,
                err,
            )
        except BridgeNotReady as err:
            _LOGGER.error("HomeKit Bridge Plus '%s' could not start: %s", bridge.name, err)

    unsub = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start)
    bridge._unsubs.append(unsub)  # noqa: SLF001

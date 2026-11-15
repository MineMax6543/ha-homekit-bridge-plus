"""Base class for entity handlers.

A *handler* binds one Home Assistant entity to one or more HomeKit services on
an accessory. Accessories are just containers; this lets us build a normal
"one entity = one accessory" setup *and* combined accessories where several
entities share one tile in the Home app.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any, Callable

from pyhap.const import CATEGORY_OTHER
from pyhap.service import Service

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Context, HomeAssistant, State

from ..const import MOMENTARY_DOMAINS
from ..util import domain_of

if TYPE_CHECKING:
    from ..accessory import HAAccessory

_LOGGER = logging.getLogger(__name__)

MOMENTARY_RESET_SECONDS = 1.0

_ON_OFF_SERVICES: dict[str, tuple[str, str]] = {
    "cover": ("open_cover", "close_cover"),
    "valve": ("open_valve", "close_valve"),
    "lock": ("unlock", "lock"),
    "vacuum": ("start", "return_to_base"),
}
_MOMENTARY_SERVICES: dict[str, str] = {
    "script": "turn_on",
    "scene": "turn_on",
    "button": "press",
    "input_button": "press",
}


class Handler:
    """Binds an entity to HomeKit services."""

    category: int = CATEGORY_OTHER

    def __init__(
        self,
        hass: HomeAssistant,
        acc: HAAccessory,
        entity_id: str,
        acc_type: str,
        cfg: dict[str, Any],
        name: str,
        state: State,
    ) -> None:
        self.hass = hass
        self.acc = acc
        self.entity_id = entity_id
        self.domain = domain_of(entity_id)
        self.acc_type = acc_type
        self.cfg = cfg
        self.name = name
        self.momentary = self.domain in MOMENTARY_DOMAINS
        self._reset_handle: asyncio.TimerHandle | None = None
        self.setup(state)

    # ---- to implement -----------------------------------------------------
    def setup(self, state: State) -> None:
        """Create services and characteristics."""
        raise NotImplementedError

    def async_update(self, state: State) -> None:
        """Push the new HA state into the HomeKit characteristics."""
        raise NotImplementedError

    # ---- helpers ----------------------------------------------------------
    def add_service(self, service: str, chars: list[str] | None = None) -> Service:
        """Add a named service to the accessory."""
        serv = self.acc.add_preload_service(
            service, [*(chars or []), "Name", "ConfiguredName"]
        )
        serv.configure_char("Name", value=self.name)
        serv.configure_char("ConfiguredName", value=self.name)
        return serv

    def set_char(self, char: Any, value: Any) -> None:
        """Set a characteristic value only when it changed."""
        if char is None or value is None:
            return
        if char.value == value:
            return
        try:
            char.set_value(value)
        except ValueError as err:
            _LOGGER.debug("%s: refusing value %s for %s: %s", self.entity_id, value, char.display_name, err)

    def call_service(
        self, domain: str, service: str, data: dict[str, Any] | None = None
    ) -> None:
        """Call a Home Assistant service (safe from any thread)."""
        payload = {ATTR_ENTITY_ID: self.entity_id, **(data or {})}

        async def _call() -> None:
            try:
                await self.hass.services.async_call(
                    domain, service, payload, blocking=True, context=Context()
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Error calling %s.%s for %s from HomeKit", domain, service, self.entity_id
                )

        # HAP-python runs setters inside HA's event loop; use a tracked task
        # there and fall back to a thread-safe hop otherwise.
        if threading.get_ident() == self.hass.loop_thread_id:
            self.hass.async_create_task(_call(), eager_start=True)
        else:
            asyncio.run_coroutine_threadsafe(_call(), self.hass.loop)

    def fire_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Fire an event on the HA bus (safe from any thread)."""
        payload = {ATTR_ENTITY_ID: self.entity_id, **data}
        if threading.get_ident() == self.hass.loop_thread_id:
            self.hass.bus.async_fire(event_type, payload)
        else:
            self.hass.loop.call_soon_threadsafe(
                self.hass.bus.async_fire, event_type, payload
            )

    def turn(self, on: bool, reset_char: Any = None, off_value: Any = False) -> None:
        """Generic on/off for any supported domain.

        For momentary domains (script, scene, button) an "on" request triggers
        the entity and the characteristic flips back after a second.
        """
        if self.momentary:
            if not on:
                return
            self.call_service(self.domain, _MOMENTARY_SERVICES[self.domain])
            if reset_char is not None:
                self._schedule_reset(reset_char, off_value)
            return
        on_service, off_service = _ON_OFF_SERVICES.get(
            self.domain, ("turn_on", "turn_off")
        )
        self.call_service(self.domain, on_service if on else off_service)

    def _schedule_reset(self, char: Any, value: Any) -> None:
        def _reset() -> None:
            self._reset_handle = None
            self.set_char(char, value)

        def _arm() -> None:
            if self._reset_handle:
                self._reset_handle.cancel()
            self._reset_handle = self.hass.loop.call_later(
                MOMENTARY_RESET_SECONDS, _reset
            )

        self.hass.loop.call_soon_threadsafe(_arm)

    def on_setter(self, func: Callable[[dict[str, Any]], None]) -> Callable[[dict[str, Any]], None]:
        """Wrap a service-level setter: normalize values, log, call.

        HAP-python hands service setters the raw values iOS sent. For bool
        characteristics iOS sends either true/false or 1/0 (the Home app does
        the latter e.g. when tapping a color light's tile), so make them real
        bools before any handler compares them.
        """
        char_types = self.acc.driver.loader.char_types

        def _wrapped(values: dict[str, Any]) -> None:
            _LOGGER.debug("%s: HomeKit set %s", self.entity_id, values)
            values = {
                name: bool(value)
                if char_types.get(name, {}).get("Format") == "bool" and value is not None
                else value
                for name, value in values.items()
            }
            func(values)

        return _wrapped

    def stop(self) -> None:
        """Cancel pending timers."""
        if self._reset_handle:
            self._reset_handle.cancel()
            self._reset_handle = None

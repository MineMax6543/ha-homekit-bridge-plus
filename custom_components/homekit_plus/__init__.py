"""HomeKit Bridge Plus: a HomeKit bridge where you choose exactly what is exposed."""

from __future__ import annotations

import logging
import os

from aiohttp import web
import voluptuous as vol

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .bridge import BridgeNotReady, HomeKitBridgePlus, async_start_when_ready
from .const import DOMAIN, QR_VIEW_URL

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type HomeKitPlusConfigEntry = ConfigEntry[HomeKitBridgePlus]

SERVICE_UNPAIR = "unpair"
UNPAIR_SCHEMA = vol.Schema({vol.Required("config_entry_id"): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the QR view and services."""
    hass.http.register_view(PairingQRView(hass))

    async def _unpair(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise ServiceValidationError("Unknown or not loaded HomeKit Bridge Plus entry")
        bridge: HomeKitBridgePlus = entry.runtime_data
        if not bridge.running:
            raise ServiceValidationError("The bridge is not running")
        bridge.async_unpair_all()

    hass.services.async_register(DOMAIN, SERVICE_UNPAIR, _unpair, schema=UNPAIR_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HomeKitPlusConfigEntry) -> bool:
    """Set up one bridge."""
    bridge = HomeKitBridgePlus(hass, entry)
    await bridge.async_setup()
    entry.runtime_data = bridge

    if hass.is_running:
        try:
            await bridge.async_start()
        except OSError as err:
            await bridge.async_stop()
            raise ConfigEntryNotReady(
                f"Could not start HomeKit bridge on port {bridge.port}: {err}"
            ) from err
        except BridgeNotReady as err:
            await bridge.async_stop()
            raise ConfigEntryNotReady(str(err)) from err
    else:
        async_start_when_ready(hass, bridge)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: HomeKitPlusConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HomeKitPlusConfigEntry) -> bool:
    """Stop the bridge."""
    bridge = entry.runtime_data
    bridge.async_dismiss_pairing()
    await bridge.async_stop()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete pairing state and AID storage."""
    path = hass.config.path(".storage", f"{DOMAIN}.{entry.entry_id}.state")

    def _remove() -> None:
        if os.path.exists(path):
            os.remove(path)

    await hass.async_add_executor_job(_remove)
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.aids").async_remove()


class PairingQRView(HomeAssistantView):
    """Serves the pairing QR code shown in the notification."""

    url = QR_VIEW_URL
    name = f"api:{DOMAIN}:pairingqr"
    requires_auth = False  # protected by a random per-start secret

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        entry_id, _, secret = request.query_string.partition("-")
        entry = self.hass.config_entries.async_get_entry(entry_id)
        bridge = getattr(entry, "runtime_data", None) if entry else None
        if (
            not isinstance(bridge, HomeKitBridgePlus)
            or not bridge.qr_svg
            or not bridge.check_qr_secret(secret)
        ):
            return web.Response(status=403)
        return web.Response(
            body=bridge.qr_svg,
            content_type="image/svg+xml",
            headers={"Cache-Control": "no-store"},
        )

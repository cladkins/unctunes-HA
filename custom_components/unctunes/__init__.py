"""UncTunes: a self-hosted Spotify jukebox venue as a Home Assistant device.

One config entry per venue. The entry's runtime data holds the API client and
the polling coordinator every platform reads from. The dashboard card ships
with the integration and is served (and, in storage mode, registered as a
Lovelace resource) from here, so installing the integration is the whole job.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import (
    UncTunesApiError,
    UncTunesAuthError,
    UncTunesClient,
    UncTunesConnectionError,
)
from .const import (
    CARD_URL,
    CONF_BASE_URL,
    CONF_TOKEN,
    CONF_VERIFY_SSL,
    DATA_FRONTEND_REGISTERED,
    DATA_SERVICES_REGISTERED,
    DOMAIN,
    FRONTEND_URL_BASE,
    PLATFORMS,
    VERSION,
)
from .coordinator import UncTunesCoordinator
from .http import async_register_views
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend"


@dataclass
class UncTunesRuntime:
    client: UncTunesClient
    coordinator: UncTunesCoordinator


UncTunesConfigEntry = ConfigEntry  # runtime_data: UncTunesRuntime


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """One-time wiring shared by every venue: card, HTTP views, services."""
    await _async_setup_frontend(hass)
    if not hass.data.get(DATA_SERVICES_REGISTERED):
        async_register_views(hass)
        async_register_services(hass)
        hass.data[DATA_SERVICES_REGISTERED] = True
    return True


async def async_setup_entry(hass: HomeAssistant, entry: UncTunesConfigEntry) -> bool:
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = UncTunesClient(
        session, entry.data[CONF_BASE_URL], entry.data[CONF_TOKEN], verify_ssl=verify_ssl
    )
    try:
        await client.async_identify()
    except UncTunesAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (UncTunesConnectionError, UncTunesApiError) as err:
        raise ConfigEntryNotReady(f"Cannot reach UncTunes at {client.base_url}: {err}") from err

    coordinator = UncTunesCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = UncTunesRuntime(client=client, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UncTunesConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: UncTunesConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ── frontend ─────────────────────────────────────────────────────────────────


async def _async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve the bundled card and register it as a Lovelace resource."""
    if hass.data.get(DATA_FRONTEND_REGISTERED):
        return
    hass.data[DATA_FRONTEND_REGISTERED] = True
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL_BASE, str(FRONTEND_DIR), cache_headers=False)]
    )
    try:
        await _async_register_card_resource(hass)
    except Exception:  # noqa: BLE001 — never let the card block the integration
        _LOGGER.warning(
            "Could not register the UncTunes card automatically; add %s as a "
            "JavaScript module under Settings → Dashboards → Resources",
            CARD_URL,
            exc_info=True,
        )


async def _async_register_card_resource(hass: HomeAssistant) -> None:
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        _LOGGER.debug("Lovelace not loaded; skipping card resource registration")
        return
    if isinstance(lovelace, dict):  # older cores kept a plain dict here
        resources = lovelace.get("resources")
    else:
        resources = getattr(lovelace, "resources", None)
    # Storage-mode resources are a StorageCollection with create/update; the
    # YAML collection has neither, and there we can only tell the user. Going by
    # capability rather than a mode attribute survives the mode → resource_mode
    # rename in core.
    if resources is None or not hasattr(resources, "async_create_item"):
        _LOGGER.info(
            "Lovelace resources are managed in YAML; add %s as a module resource by hand",
            CARD_URL,
        )
        return
    if hasattr(resources, "loaded") and not resources.loaded:
        await resources.async_load()

    versioned = f"{CARD_URL}?v={VERSION}"
    for item in resources.async_items():
        url = str(item.get("url") or "")
        if url.split("?", 1)[0] != CARD_URL:
            continue
        if url != versioned:
            await resources.async_update_item(item["id"], {"url": versioned})
            _LOGGER.info("Updated UncTunes card resource to %s", versioned)
        return
    await resources.async_create_item({"res_type": "module", "url": versioned})
    _LOGGER.info("Registered UncTunes card resource %s", versioned)

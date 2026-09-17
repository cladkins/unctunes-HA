"""Polling coordinator: one snapshot per interval feeds every entity."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    UncTunesApiError,
    UncTunesAuthError,
    UncTunesClient,
    UncTunesConnectionError,
)
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class UncTunesCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches the venue snapshot on a fixed interval."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: UncTunesClient
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.venue_name or client.slug}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        # When the player progress in .data was read, for position interpolation.
        self.fetched_at = dt_util.utcnow()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.async_snapshot()
        except UncTunesAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except UncTunesConnectionError as err:
            raise UpdateFailed(f"Cannot reach UncTunes: {err}") from err
        except UncTunesApiError as err:
            raise UpdateFailed(f"UncTunes error {err.status}: {err.message}") from err
        self.fetched_at = dt_util.utcnow()
        return data

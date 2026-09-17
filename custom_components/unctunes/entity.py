"""Shared entity base: one device per venue."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import UncTunesCoordinator


class UncTunesEntity(CoordinatorEntity[UncTunesCoordinator]):
    """Base for every UncTunes entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: UncTunesCoordinator, key: str) -> None:
        super().__init__(coordinator)
        client = coordinator.client
        self._attr_unique_id = f"{client.venue_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, client.venue_id or "")},
            name=client.venue_name or "UncTunes",
            manufacturer="UncTunes",
            model="Jukebox venue",
            sw_version=VERSION,
            configuration_url=client.dashboard_url,
        )

    @property
    def data(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.data)

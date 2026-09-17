"""Switches for the venue settings a host flips day to day."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import UncTunesApiError, UncTunesClient, UncTunesConnectionError
from .coordinator import UncTunesCoordinator
from .entity import UncTunesEntity


@dataclass(frozen=True, kw_only=True)
class UncTunesSwitchDescription(SwitchEntityDescription):
    is_on_fn: Callable[[dict[str, Any]], bool]
    set_fn: Callable[[UncTunesClient, bool], Awaitable[Any]]


def _settings(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("settings") or {}


SWITCHES: tuple[UncTunesSwitchDescription, ...] = (
    UncTunesSwitchDescription(
        key="autoplay",
        translation_key="autoplay",
        icon="mdi:shuffle-variant",
        is_on_fn=lambda d: bool((_settings(d).get("autoplay") or {}).get("enabled")),
        set_fn=lambda c, on: c.async_update_settings({"autoplay": {"enabled": on}}),
    ),
    UncTunesSwitchDescription(
        key="auto_advance",
        translation_key="auto_advance",
        icon="mdi:play-speed",
        is_on_fn=lambda d: bool(d.get("autoAdvance")),
        set_fn=lambda c, on: c.async_set_auto_advance(on),
    ),
    UncTunesSwitchDescription(
        key="device_lock",
        translation_key="device_lock",
        icon="mdi:speaker-off",
        entity_registry_enabled_default=False,
        is_on_fn=lambda d: bool((_settings(d).get("deviceLock") or {}).get("enabled")),
        set_fn=lambda c, on: c.async_update_settings({"deviceLock": {"enabled": on}}),
    ),
    UncTunesSwitchDescription(
        key="qr_join",
        translation_key="qr_join",
        icon="mdi:qrcode-scan",
        entity_registry_enabled_default=False,
        is_on_fn=lambda d: bool(_settings(d).get("joinEnabled")),
        set_fn=lambda c, on: c.async_update_settings({"joinEnabled": on}),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: UncTunesCoordinator = entry.runtime_data.coordinator
    async_add_entities(UncTunesSwitch(coordinator, desc) for desc in SWITCHES)


class UncTunesSwitch(UncTunesEntity, SwitchEntity):
    entity_description: UncTunesSwitchDescription

    def __init__(
        self, coordinator: UncTunesCoordinator, description: UncTunesSwitchDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.data)

    async def _set(self, on: bool) -> None:
        try:
            await self.entity_description.set_fn(self.coordinator.client, on)
        except UncTunesApiError as err:
            raise HomeAssistantError(err.message) from err
        except UncTunesConnectionError as err:
            raise HomeAssistantError(f"Cannot reach UncTunes: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

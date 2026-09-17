"""Buttons: one-shot host actions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import UncTunesApiError, UncTunesClient, UncTunesConnectionError
from .coordinator import UncTunesCoordinator
from .entity import UncTunesEntity


@dataclass(frozen=True, kw_only=True)
class UncTunesButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[UncTunesClient], Awaitable[Any]]


BUTTONS: tuple[UncTunesButtonDescription, ...] = (
    UncTunesButtonDescription(
        key="skip",
        translation_key="skip",
        icon="mdi:skip-next",
        press_fn=lambda c: c.async_skip(),
    ),
    UncTunesButtonDescription(
        key="play_next",
        translation_key="play_next",
        icon="mdi:play-circle",
        press_fn=lambda c: c.async_play_next(),
    ),
    UncTunesButtonDescription(
        key="clear_queue",
        translation_key="clear_queue",
        icon="mdi:playlist-remove",
        press_fn=lambda c: c.async_clear_queue(),
    ),
    UncTunesButtonDescription(
        key="pool_sync",
        translation_key="pool_sync",
        icon="mdi:sync",
        entity_registry_enabled_default=False,
        press_fn=lambda c: c.async_pool_sync(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: UncTunesCoordinator = entry.runtime_data.coordinator
    async_add_entities(UncTunesButton(coordinator, desc) for desc in BUTTONS)


class UncTunesButton(UncTunesEntity, ButtonEntity):
    entity_description: UncTunesButtonDescription

    def __init__(
        self, coordinator: UncTunesCoordinator, description: UncTunesButtonDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        try:
            await self.entity_description.press_fn(self.coordinator.client)
        except UncTunesApiError as err:
            raise HomeAssistantError(err.message) from err
        except UncTunesConnectionError as err:
            raise HomeAssistantError(f"Cannot reach UncTunes: {err}") from err
        await self.coordinator.async_request_refresh()

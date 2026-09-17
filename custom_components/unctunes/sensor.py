"""Sensors: queue length, who asked for the current song, what's next."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import UncTunesCoordinator
from .entity import UncTunesEntity


@dataclass(frozen=True, kw_only=True)
class UncTunesSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _next_up(data: dict[str, Any]) -> str | None:
    queue = data.get("queue") or []
    if not queue or not queue[0].get("track"):
        return None
    track = queue[0]["track"]
    return f"{track.get('name')} – {track.get('artist')}"


def _next_up_attrs(data: dict[str, Any]) -> dict[str, Any]:
    queue = data.get("queue") or []
    if not queue:
        return {}
    entry = queue[0]
    track = entry.get("track") or {}
    return {
        "requester": entry.get("requester"),
        "priority": bool(entry.get("priority")),
        "album_art": track.get("albumArt"),
        "uri": track.get("uri"),
    }


def _requester(data: dict[str, Any]) -> str | None:
    current = data.get("currentTrack") or {}
    return current.get("requester")


def _selected_device(data: dict[str, Any]) -> str | None:
    selected = data.get("selectedDevice") or {}
    return selected.get("name") or ("Unnamed device" if selected.get("id") else None)


def _selected_device_attrs(data: dict[str, Any]) -> dict[str, Any]:
    selected = data.get("selectedDevice") or {}
    devices = data.get("devices") or []
    online = [d.get("name") for d in devices if not d.get("offline")]
    return {
        "device_id": selected.get("id"),
        "online_devices": [n for n in online if n],
        "playing_on": ((data.get("player") or {}).get("device") or {}).get("name"),
    }


SENSORS: tuple[UncTunesSensorDescription, ...] = (
    UncTunesSensorDescription(
        key="queue_length",
        translation_key="queue_length",
        icon="mdi:playlist-music",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.get("queue") or []),
    ),
    UncTunesSensorDescription(
        key="requester",
        translation_key="requester",
        icon="mdi:account-music",
        value_fn=_requester,
    ),
    UncTunesSensorDescription(
        key="next_up",
        translation_key="next_up",
        icon="mdi:skip-next-circle-outline",
        value_fn=_next_up,
        attrs_fn=_next_up_attrs,
    ),
    UncTunesSensorDescription(
        key="playback_device",
        translation_key="playback_device",
        icon="mdi:speaker",
        value_fn=_selected_device,
        attrs_fn=_selected_device_attrs,
    ),
    UncTunesSensorDescription(
        key="pending_members",
        translation_key="pending_members",
        icon="mdi:account-clock",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("pendingCount"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: UncTunesCoordinator = entry.runtime_data.coordinator
    async_add_entities(UncTunesSensor(coordinator, desc) for desc in SENSORS)


class UncTunesSensor(UncTunesEntity, SensorEntity):
    entity_description: UncTunesSensorDescription

    def __init__(
        self, coordinator: UncTunesCoordinator, description: UncTunesSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.data)

"""Media player: the venue's jukebox as one player entity."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEnqueue,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import UncTunesApiError, UncTunesConnectionError
from .const import DEFAULT_REQUESTER, DOMAIN, QUEUE_ATTRIBUTE_LIMIT
from .coordinator import UncTunesCoordinator
from .entity import UncTunesEntity
from .helpers import looks_like_spotify_track, queue_entry_view

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: UncTunesCoordinator = entry.runtime_data.coordinator
    async_add_entities([UncTunesMediaPlayer(coordinator, entry)])


class UncTunesMediaPlayer(UncTunesEntity, MediaPlayerEntity):
    """The venue's Spotify playback, as UncTunes sees and controls it."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_media_content_type = MediaType.MUSIC
    _attr_media_image_remotely_accessible = True
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.CLEAR_PLAYLIST
    )

    def __init__(self, coordinator: UncTunesCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, "player")
        self._entry = entry

    # ── derived views of the snapshot ────────────────────────────────────────

    @property
    def _player(self) -> dict[str, Any]:
        return self.data.get("player") or {}

    @property
    def _item(self) -> dict[str, Any] | None:
        """What Spotify says is loaded, falling back to the queue's idea."""
        item = self._player.get("item")
        if item:
            return item
        current = self.data.get("currentTrack") or {}
        return current.get("track")

    @property
    def _current_entry(self) -> dict[str, Any] | None:
        return self.data.get("currentTrack")

    # ── state ────────────────────────────────────────────────────────────────

    @property
    def state(self) -> MediaPlayerState:
        spotify = self.data.get("spotify") or {}
        if not spotify.get("connected"):
            return MediaPlayerState.OFF
        player = self._player
        if not player.get("item"):
            return MediaPlayerState.IDLE
        return (
            MediaPlayerState.PLAYING
            if player.get("isPlaying")
            else MediaPlayerState.PAUSED
        )

    @property
    def media_title(self) -> str | None:
        item = self._item
        return item.get("name") if item else None

    @property
    def media_artist(self) -> str | None:
        item = self._item
        return item.get("artist") if item else None

    @property
    def media_album_name(self) -> str | None:
        item = self._item
        return item.get("album") if item else None

    @property
    def media_image_url(self) -> str | None:
        item = self._item
        if not item:
            return None
        return item.get("albumArtLarge") or item.get("albumArt")

    @property
    def media_content_id(self) -> str | None:
        item = self._item
        return item.get("uri") if item else None

    @property
    def media_duration(self) -> int | None:
        ms = self._player.get("durationMs")
        if not ms:
            item = self._item
            ms = item.get("duration") if item else None
        return int(ms / 1000) if ms else None

    @property
    def media_position(self) -> int | None:
        if not self._player.get("item"):
            return None
        return int((self._player.get("progressMs") or 0) / 1000)

    @property
    def media_position_updated_at(self):
        if not self._player.get("item"):
            return None
        return self.coordinator.fetched_at

    @property
    def volume_level(self) -> float | None:
        volume = self._player.get("volume")
        if volume is None:
            selected = self.data.get("selectedDevice") or {}
            for device in self.data.get("devices") or []:
                if device.get("id") == selected.get("id") and device.get("volume") is not None:
                    volume = device["volume"]
                    break
        return None if volume is None else max(0.0, min(1.0, volume / 100))

    @property
    def source(self) -> str | None:
        selected = self.data.get("selectedDevice") or {}
        return selected.get("name")

    @property
    def source_list(self) -> list[str] | None:
        names: list[str] = []
        for device in self.data.get("devices") or []:
            name = device.get("name")
            if name and name not in names:
                names.append(name)
        return names or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.data
        current = self._current_entry or {}
        queue = data.get("queue") or []
        settings = data.get("settings") or {}
        autoplay = settings.get("autoplay") or {}
        pool = data.get("pool") or None
        window = data.get("window") or {}
        next_entry = queue[0] if queue else None
        return {
            "entry_id": self._entry.entry_id,
            "venue_slug": (data.get("venue") or {}).get("slug"),
            "requester": current.get("requester"),
            "is_autoplay": bool(current.get("autoplay")),
            "queue_length": len(queue),
            "queue": [queue_entry_view(e, i + 1) for i, e in enumerate(queue[:QUEUE_ATTRIBUTE_LIMIT])],
            "next_up": (
                f"{next_entry['track'].get('name')} – {next_entry['track'].get('artist')}"
                if next_entry and next_entry.get("track")
                else None
            ),
            "autoplay_enabled": bool(autoplay.get("enabled")),
            "autoplay_playlist": autoplay.get("playlistName"),
            "auto_advance": bool(data.get("autoAdvance")),
            "device_lock": bool((settings.get("deviceLock") or {}).get("enabled")),
            "requests_open": bool(window.get("open", True)),
            "pool": pool.get("name") if pool else None,
            "pending_members": data.get("pendingCount"),
            "spotify_account": (data.get("spotify") or {}).get("account"),
        }

    # ── commands ─────────────────────────────────────────────────────────────

    async def _run(self, coro) -> Any:
        try:
            result = await coro
        except UncTunesApiError as err:
            raise HomeAssistantError(err.message) from err
        except UncTunesConnectionError as err:
            raise HomeAssistantError(f"Cannot reach UncTunes: {err}") from err
        await self.coordinator.async_request_refresh()
        return result

    async def async_media_play(self) -> None:
        # Nothing loaded yet → "play" means start the queue (or autoplay).
        if not self._player.get("item"):
            await self._run(self.coordinator.client.async_play_next())
            return
        await self._run(self.coordinator.client.async_resume())

    async def async_media_pause(self) -> None:
        await self._run(self.coordinator.client.async_pause())

    async def async_media_next_track(self) -> None:
        await self._run(self.coordinator.client.async_skip())

    async def async_set_volume_level(self, volume: float) -> None:
        await self._run(self.coordinator.client.async_set_volume(round(volume * 100)))

    async def async_select_source(self, source: str) -> None:
        for device in self.data.get("devices") or []:
            if device.get("name") == source:
                await self._run(self.coordinator.client.async_select_device(device.get("id")))
                return
        raise HomeAssistantError(f"Unknown playback device: {source}")

    async def async_clear_playlist(self) -> None:
        await self._run(self.coordinator.client.async_clear_queue())

    async def async_play_media(
        self,
        media_type: str,
        media_id: str,
        enqueue: MediaPlayerEnqueue | None = None,
        announce: bool | None = None,
        **kwargs: Any,
    ) -> None:
        """Queue a song. media_id is a Spotify track URI/link/id, or a search."""
        client = self.coordinator.client
        uri = media_id.strip()
        if not looks_like_spotify_track(uri):
            try:
                results = await client.async_search(uri, limit=1)
            except UncTunesConnectionError as err:
                raise HomeAssistantError(f"Cannot reach UncTunes: {err}") from err
            except UncTunesApiError as err:
                raise HomeAssistantError(err.message) from err
            if not results:
                raise HomeAssistantError(f"No Spotify track found for '{media_id}'")
            uri = results[0]["uri"]
        priority = enqueue in (MediaPlayerEnqueue.NEXT, MediaPlayerEnqueue.PLAY)
        requester = kwargs.get("extra", {}).get("requester") if isinstance(kwargs.get("extra"), dict) else None
        await self._run(
            client.async_request_track(
                uri, priority=priority, requester=requester or DEFAULT_REQUESTER
            )
        )
        if enqueue is MediaPlayerEnqueue.PLAY:
            await self._run(client.async_play_next())

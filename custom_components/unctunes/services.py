"""Domain services: request a song, search Spotify."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import UncTunesApiError, UncTunesConnectionError
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_LIMIT,
    ATTR_PRIORITY,
    ATTR_QUERY,
    ATTR_REQUESTER,
    ATTR_URI,
    DEFAULT_REQUESTER,
    DOMAIN,
    SERVICE_REQUEST_SONG,
    SERVICE_SEARCH,
)
from .helpers import looks_like_spotify_track

REQUEST_SONG_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
            vol.Optional(ATTR_QUERY): cv.string,
            vol.Optional(ATTR_URI): cv.string,
            vol.Optional(ATTR_PRIORITY, default=False): cv.boolean,
            vol.Optional(ATTR_REQUESTER): cv.string,
        }
    ),
    cv.has_at_least_one_key(ATTR_QUERY, ATTR_URI),
)

SEARCH_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_QUERY): cv.string,
        vol.Optional(ATTR_LIMIT, default=10): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
    }
)


def _entry_for_call(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry:
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    loaded = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED
    ]
    if entry_id:
        for entry in loaded:
            if entry.entry_id == entry_id:
                return entry
        raise ServiceValidationError(f"No loaded UncTunes venue with config entry id {entry_id}")
    if len(loaded) == 1:
        return loaded[0]
    if not loaded:
        raise ServiceValidationError("No UncTunes venue is set up")
    raise ServiceValidationError(
        "Several UncTunes venues are set up; pass config_entry_id to pick one"
    )


async def _async_request_song(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    entry = _entry_for_call(hass, call)
    runtime = entry.runtime_data
    client = runtime.client
    uri = (call.data.get(ATTR_URI) or "").strip()
    query = (call.data.get(ATTR_QUERY) or "").strip()
    try:
        if not uri:
            if looks_like_spotify_track(query):
                uri = query
            else:
                results = await client.async_search(query, limit=1)
                if not results:
                    raise ServiceValidationError(f"No Spotify track found for '{query}'")
                uri = results[0]["uri"]
        result = await client.async_request_track(
            uri,
            priority=bool(call.data.get(ATTR_PRIORITY)),
            requester=(call.data.get(ATTR_REQUESTER) or DEFAULT_REQUESTER).strip()[:40],
        )
    except UncTunesApiError as err:
        raise HomeAssistantError(err.message) from err
    except UncTunesConnectionError as err:
        raise HomeAssistantError(f"Cannot reach UncTunes: {err}") from err
    await runtime.coordinator.async_request_refresh()
    entry_data = result.get("entry") or {}
    track = entry_data.get("track") or {}
    return {
        "queued": bool(result.get("success")),
        "position": result.get("position"),
        "title": track.get("name"),
        "artist": track.get("artist"),
        "uri": track.get("uri"),
        "requester": entry_data.get("requester"),
    }


async def _async_search(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    entry = _entry_for_call(hass, call)
    try:
        tracks = await entry.runtime_data.client.async_search(
            call.data[ATTR_QUERY], limit=call.data[ATTR_LIMIT]
        )
    except UncTunesApiError as err:
        raise HomeAssistantError(err.message) from err
    except UncTunesConnectionError as err:
        raise HomeAssistantError(f"Cannot reach UncTunes: {err}") from err
    return {
        "tracks": [
            {
                "title": t.get("name"),
                "artist": t.get("artist"),
                "album": t.get("album"),
                "uri": t.get("uri"),
                "duration_ms": t.get("duration"),
                "album_art": t.get("albumArt"),
                "explicit": bool(t.get("explicit")),
            }
            for t in tracks
        ]
    }


def async_register_services(hass: HomeAssistant) -> None:
    async def request_song(call: ServiceCall) -> ServiceResponse:
        return await _async_request_song(hass, call)

    async def search(call: ServiceCall) -> ServiceResponse:
        return await _async_search(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_REQUEST_SONG,
        request_song,
        schema=REQUEST_SONG_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH,
        search,
        schema=SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

"""HTTP views behind the dashboard card.

The card runs in a browser that is logged into Home Assistant, never into
UncTunes, so search and song requests go through these views: HA checks the
browser's auth, the integration signs the call to UncTunes with its venue
token. That keeps the venue token on the HA server and lets a walk-up kiosk
user (any HA user, admin or not) add songs.
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from .api import UncTunesApiError, UncTunesConnectionError
from .const import DEFAULT_REQUESTER, DOMAIN
from .helpers import queue_entry_view

_LOGGER = logging.getLogger(__name__)

MAX_REQUESTER_LEN = 40


def _loaded_entry(hass: HomeAssistant, entry_id: str) -> ConfigEntry | None:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        return None
    return entry


class _BaseView(HomeAssistantView):
    requires_auth = True

    def _entry(self, request: web.Request, entry_id: str) -> ConfigEntry:
        entry = _loaded_entry(request.app[KEY_HASS], entry_id)
        if entry is None:
            raise web.HTTPNotFound(text="Unknown UncTunes venue")
        return entry


class UncTunesSearchView(_BaseView):
    url = "/api/unctunes/{entry_id}/search"
    name = "api:unctunes:search"

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        entry = self._entry(request, entry_id)
        query = (request.query.get("q") or "").strip()
        if not query:
            return self.json({"tracks": []})
        try:
            tracks = await entry.runtime_data.client.async_search(query)
        except UncTunesApiError as err:
            return self.json_message(err.message, status_code=err.status)
        except UncTunesConnectionError as err:
            return self.json_message(f"Cannot reach UncTunes: {err}", status_code=502)
        return self.json({"tracks": tracks})


class UncTunesRequestView(_BaseView):
    url = "/api/unctunes/{entry_id}/request"
    name = "api:unctunes:request"

    async def post(self, request: web.Request, entry_id: str) -> web.Response:
        entry = self._entry(request, entry_id)
        try:
            body: dict[str, Any] = await request.json()
        except ValueError:
            return self.json_message("Invalid JSON", status_code=400)
        uri = str(body.get("uri") or "").strip()
        if not uri:
            return self.json_message("uri is required", status_code=400)
        requester = str(body.get("requester") or "").strip()[:MAX_REQUESTER_LEN] or DEFAULT_REQUESTER
        priority = bool(body.get("priority"))
        runtime = entry.runtime_data
        try:
            result = await runtime.client.async_request_track(
                uri, priority=priority, requester=requester
            )
        except UncTunesApiError as err:
            return self.json_message(err.message, status_code=err.status)
        except UncTunesConnectionError as err:
            return self.json_message(f"Cannot reach UncTunes: {err}", status_code=502)
        await runtime.coordinator.async_request_refresh()
        return self.json(result)


class UncTunesStateView(_BaseView):
    """The full queue for the card (state attributes carry a trimmed copy)."""

    url = "/api/unctunes/{entry_id}/state"
    name = "api:unctunes:state"

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        entry = self._entry(request, entry_id)
        data = entry.runtime_data.coordinator.data or {}
        queue = data.get("queue") or []
        return self.json(
            {
                "venue": data.get("venue"),
                "currentTrack": data.get("currentTrack"),
                "player": data.get("player"),
                "queue": [queue_entry_view(e, i + 1) for i, e in enumerate(queue)],
                "window": data.get("window"),
                "spotify": data.get("spotify"),
            }
        )


def async_register_views(hass: HomeAssistant) -> None:
    hass.http.register_view(UncTunesSearchView())
    hass.http.register_view(UncTunesRequestView())
    hass.http.register_view(UncTunesStateView())

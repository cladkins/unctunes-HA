"""Thin async client for the UncTunes venue API.

Authenticates with a venue API token (minted on the host dashboard under
Settings → Integrations). The token stands in for the venue's host, so every
call here lands on the same routes the dashboard uses.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class UncTunesError(Exception):
    """Base error."""


class UncTunesConnectionError(UncTunesError):
    """The server could not be reached."""


class UncTunesAuthError(UncTunesError):
    """The token was rejected."""


class UncTunesApiError(UncTunesError):
    """The server answered with an error."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class UncTunesClient:
    """Async client bound to one venue token."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        token: str,
        *,
        verify_ssl: bool = True,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._token = token
        self._verify_ssl = verify_ssl
        self.venue: dict[str, Any] = {}
        self.token_info: dict[str, Any] = {}

    @property
    def base_url(self) -> str:
        return self._base

    @property
    def slug(self) -> str | None:
        return self.venue.get("slug")

    @property
    def venue_id(self) -> str | None:
        return self.venue.get("id")

    @property
    def venue_name(self) -> str | None:
        return self.venue.get("name")

    @property
    def dashboard_url(self) -> str | None:
        if not self.slug:
            return None
        return f"{self._base}/v/{self.slug}/host"

    # ── transport ────────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        try:
            async with self._session.request(
                method,
                url,
                json=json,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                ssl=None if self._verify_ssl else False,
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                if resp.status == 401:
                    raise UncTunesAuthError(data.get("error") or "Invalid API token")
                if resp.status >= 400:
                    raise UncTunesApiError(
                        resp.status, data.get("error") or f"HTTP {resp.status}"
                    )
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise UncTunesConnectionError(str(err) or err.__class__.__name__) from err

    def _v(self, path: str) -> str:
        if not self.slug:
            raise UncTunesError("Venue not identified yet; call async_identify first")
        return f"/v/{self.slug}{path}"

    # ── identity ─────────────────────────────────────────────────────────────

    async def async_identify(self) -> dict[str, Any]:
        """Resolve the token to its venue. Sets .venue for later calls."""
        data = await self._request("GET", "/api/integrations/v1/me")
        venue = data.get("venue") or {}
        if not venue.get("slug") or not venue.get("id"):
            raise UncTunesApiError(500, "Server did not describe a venue")
        self.venue = venue
        self.token_info = data.get("token") or {}
        return venue

    # ── reads ────────────────────────────────────────────────────────────────

    async def async_snapshot(self) -> dict[str, Any]:
        return await self._request("GET", self._v("/api/host/snapshot"))

    async def async_search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        data = await self._request("GET", self._v("/api/search"), params={"q": query})
        tracks = data.get("tracks") or []
        return tracks[: max(1, limit)]

    # ── queue ────────────────────────────────────────────────────────────────

    async def async_request_track(
        self,
        uri: str,
        *,
        priority: bool = False,
        requester: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"uri": uri, "priority": bool(priority)}
        if requester:
            body["requester"] = requester
        return await self._request("POST", self._v("/api/queue"), json=body)

    async def async_remove_queue_entry(self, entry_id: str) -> None:
        await self._request("DELETE", self._v(f"/api/queue/{entry_id}"))

    async def async_clear_queue(self) -> None:
        await self._request("DELETE", self._v("/api/queue"))

    # ── playback ─────────────────────────────────────────────────────────────

    async def async_play_next(self) -> dict[str, Any]:
        return await self._request("POST", self._v("/api/host/play-next"))

    async def async_skip(self) -> dict[str, Any]:
        return await self._request("POST", self._v("/api/host/skip"))

    async def async_pause(self) -> None:
        await self._request("POST", self._v("/api/host/pause"))

    async def async_resume(self) -> None:
        await self._request("POST", self._v("/api/host/resume"))

    async def async_set_volume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        await self._request("POST", self._v("/api/host/volume"), json={"volume": volume})

    async def async_select_device(self, device_id: str | None) -> None:
        await self._request(
            "POST", self._v("/api/host/devices/select"), json={"deviceId": device_id}
        )

    async def async_set_auto_advance(self, enabled: bool) -> None:
        await self._request(
            "POST", self._v("/api/host/auto-advance"), json={"enabled": bool(enabled)}
        )

    async def async_update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", self._v("/api/host/settings"), json=patch)

    async def async_pool_sync(self) -> None:
        await self._request("POST", self._v("/api/host/pool/sync"))

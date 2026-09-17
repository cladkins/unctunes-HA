"""Small shared helpers."""

from __future__ import annotations

import re
from typing import Any

_TRACK_URI = re.compile(r"^spotify:track:[A-Za-z0-9]{22}$")
_TRACK_LINK = re.compile(r"open\.spotify\.com/(?:intl-[a-z]+/)?track/[A-Za-z0-9]{22}")
_TRACK_ID = re.compile(r"^[A-Za-z0-9]{22}$")


def looks_like_spotify_track(value: str) -> bool:
    """True for a track URI, an open.spotify.com track link, or a bare id."""
    value = value.strip()
    return bool(_TRACK_URI.match(value) or _TRACK_LINK.search(value) or _TRACK_ID.match(value))


def queue_entry_view(entry: dict[str, Any], position: int) -> dict[str, Any]:
    """Compact queue entry for state attributes and the card."""
    track = entry.get("track") or {}
    return {
        "id": entry.get("id"),
        "position": position,
        "title": track.get("name"),
        "artist": track.get("artist"),
        "album_art": track.get("albumArt"),
        "duration": track.get("duration"),
        "uri": track.get("uri"),
        "requester": entry.get("requester"),
        "priority": bool(entry.get("priority")),
        "autoplay": bool(entry.get("autoplay")),
    }

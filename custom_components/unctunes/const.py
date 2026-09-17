"""Constants for the UncTunes integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "unctunes"
VERSION = "0.1.0"

CONF_BASE_URL = "base_url"
CONF_TOKEN = "token"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 5
MIN_SCAN_INTERVAL = 2
MAX_SCAN_INTERVAL = 60

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
]

# The dashboard card ships inside the integration and is served from here.
FRONTEND_URL_BASE = "/unctunes-static"
CARD_FILENAME = "unctunes-card.js"
CARD_URL = f"{FRONTEND_URL_BASE}/{CARD_FILENAME}"

# hass.data keys for one-time setup (static path, views, services).
DATA_FRONTEND_REGISTERED = f"{DOMAIN}_frontend_registered"
DATA_SERVICES_REGISTERED = f"{DOMAIN}_services_registered"

# How many queue entries ride along as media_player attributes. The full queue
# is available to the card through the integration's own HTTP view.
QUEUE_ATTRIBUTE_LIMIT = 15

SERVICE_REQUEST_SONG = "request_song"
SERVICE_SEARCH = "search"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_QUERY = "query"
ATTR_URI = "uri"
ATTR_PRIORITY = "priority"
ATTR_REQUESTER = "requester"
ATTR_LIMIT = "limit"

DEFAULT_REQUESTER = "Home Assistant"

# UncTunes for Home Assistant

A custom integration and dashboard card that put an [UncTunes](https://github.com/cladkins/unctunes-prod) venue on your Home Assistant.

- **Walk-up jukebox card**: guests search Spotify on a wall tablet or kiosk and add songs to the venue's shared queue. They see what's playing, who asked for it, and what's next.
- **Host stays in control**: everything rides on the real UncTunes queue. Skip, pause, volume, sin bin, and approvals all keep working from the UncTunes host dashboard. The card hides host controls by default.
- **Entities for automations**: a media player, queue and now-playing sensors, switches for autoplay and auto-advance, and buttons for skip and play next.
- **Actions**: `unctunes.request_song` and `unctunes.search` for scripts and automations.

## Requirements

- Home Assistant 2025.1 or newer.
- An UncTunes server running a build that includes venue API tokens (Settings → Integrations on the host dashboard).
- Home Assistant must be able to reach the UncTunes URL. The venue's Spotify connection stays on the UncTunes server; Home Assistant never talks to Spotify.

## Install

### HACS

1. HACS → Integrations → three-dot menu → **Custom repositories**.
2. Add `https://github.com/cladkins/unctunes-ha` with category **Integration**.
3. Install **UncTunes**, then restart Home Assistant.

### Manual

Copy `custom_components/unctunes` into your Home Assistant `config/custom_components/` directory and restart.

## Set up a venue

1. On the UncTunes host dashboard open **Settings → Integrations**, name a token (for example "Home Assistant") and click **Create token**. Copy it. You will not see it again.
2. In Home Assistant go to **Settings → Devices & services → Add integration → UncTunes**.
3. Enter your UncTunes URL (for example `https://unctunes.example.com`) and paste the token.

The integration finds the venue from the token. One config entry per venue, so a multi-venue account adds the integration once per venue, each with its own token.

Revoking the token on the host dashboard cuts Home Assistant off immediately. Home Assistant then asks you to re-authenticate with a new token.

## The dashboard card

The card is bundled with the integration and served at `/unctunes-static/unctunes-card.js`. When your dashboards are in storage mode (the default), the integration registers that resource for you. If you manage resources in YAML, add:

```yaml
resources:
  - url: /unctunes-static/unctunes-card.js?v=0.1.1
    type: module
```

Then add a card: **Edit dashboard → Add card → UncTunes Jukebox**. The visual editor covers every option.

```yaml
type: custom:unctunes-card
entity: media_player.the_dive_bar
show_search: true
show_queue: true
show_now_playing: true
show_controls: false
show_speaker: false
allow_priority: false
ask_name: false
requester: Jukebox
queue_limit: 10
idle_reset: 45
```

| Option | Default | What it does |
|---|---|---|
| `entity` | required | The venue's `media_player` entity. |
| `title` | venue name | Card heading. |
| `show_now_playing` | `true` | Album art, title, artist, requester, and a progress bar. |
| `show_search` | `true` | The search box and results with **+ Add** buttons. |
| `show_queue` | `true` | The upcoming queue with positions and requesters. |
| `show_controls` | `false` | Pause, skip, and volume. Leave off on a public kiosk. |
| `show_speaker` | `false` | A dropdown of the venue's Spotify devices. Picking one selects it on UncTunes, the same as the dashboard's Playback Device picker, with no UncTunes login. |
| `allow_priority` | `false` | Adds a ⚡ button that puts the song at the front of the queue. |
| `ask_name` | `false` | Shows a name field so the queue reads "Table 4" instead of the default requester. Remembered per browser. |
| `requester` | `Jukebox` | Name attached to requests when no guest name is given. |
| `queue_limit` | `10` | Rows of the queue to show. `0` shows all of them. |
| `idle_reset` | `45` | Seconds of inactivity before the search clears itself. `0` disables. |

### Kiosk notes

- The browser on the tablet must be logged into Home Assistant. Any user works; admin is not needed. The venue token never leaves the Home Assistant server.
- Pair the card with a kiosk-mode dashboard (for example the Kiosk Mode HACS plugin, or a browser in fullscreen) so guests only see the jukebox.
- Requests made from the card bypass guest credits and allowed-hours gating, in the same way the host's own requests do. When allowed hours are on and the window is closed, the card shows a notice.

## Entities

One device per venue with:

| Entity | Notes |
|---|---|
| `media_player.<venue>` | State playing / paused / idle / off. Title, artist, album art, position. Volume, source (playback device), play/pause/next, `play_media` with a Spotify URI or a search phrase, `clear_playlist` clears the queue. Attributes carry the queue (first 15 rows), requester, next up, autoplay, pool, and pending member count. |
| `sensor.<venue>_queue_length` | Songs waiting. |
| `sensor.<venue>_requested_by` | Who asked for the current song. |
| `sensor.<venue>_next_up` | "Title – Artist" of the next song. |
| `sensor.<venue>_playback_device` | Selected Spotify device. |
| `sensor.<venue>_pending_join_requests` | Guests waiting for approval. |
| `switch.<venue>_autoplay` | The jukebox filler playlist on or off. |
| `switch.<venue>_auto_advance` | Server-side auto-advance at track end. |
| `switch.<venue>_device_lock`, `switch.<venue>_qr_joining` | Disabled by default. Enable them under the device page if you want them. |
| `button.<venue>_skip`, `button.<venue>_play_next_in_queue`, `button.<venue>_clear_queue` | One-shot host actions. |
| `button.<venue>_sync_pool` | Disabled by default. Only useful when the venue is in a queue pool. |

## Actions

### `unctunes.request_song`

```yaml
action: unctunes.request_song
data:
  query: "Mr. Brightside The Killers"   # or uri: spotify:track:…
  priority: false
  requester: "Happy hour bot"
```

Returns `queued`, `position`, `title`, `artist`, `uri`, and `requester` when you use `response_variable`.

### `unctunes.search`

```yaml
action: unctunes.search
data:
  query: "Dancing Queen"
  limit: 5
response_variable: results
```

Returns a `tracks` list with `title`, `artist`, `album`, `uri`, `duration_ms`, `album_art`, and `explicit`.

Both actions take an optional `config_entry_id` to pick a venue when more than one is set up.

### Example: happy hour opener

```yaml
automation:
  - alias: Kick off happy hour
    triggers:
      - trigger: time
        at: "17:00:00"
    actions:
      - action: unctunes.request_song
        data:
          uri: spotify:track:3n3Ppam7vgaVa1iaRUc9Lp
          priority: true
          requester: Happy hour
      - action: button.press
        target:
          entity_id: button.the_dive_bar_play_next_in_queue
```

## How it talks to UncTunes

The integration polls `/v/<slug>/api/host/snapshot` every 5 seconds (adjustable under the integration's options) with a bearer token, and calls the same host endpoints the dashboard uses for actions. Search and card requests go through Home Assistant's own HTTP layer (`/api/unctunes/<entry_id>/search` and `/request`), so the browser authenticates to Home Assistant and Home Assistant authenticates to UncTunes.

## Development

No build step. Edit the Python under `custom_components/unctunes/` and the card at `custom_components/unctunes/frontend/unctunes-card.js`, restart Home Assistant, and hard-refresh the dashboard. Bump `VERSION` in `const.py` and `manifest.json` together; the version is appended to the card resource URL so browsers pick up the new file.

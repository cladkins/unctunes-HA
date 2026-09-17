/*
 * UncTunes Jukebox card for Home Assistant.
 *
 * A walk-up panel for a venue: guests search Spotify and add songs to the
 * venue's shared queue, see what's playing and what's next. Host controls
 * (pause, skip, volume) are off by default so a wall tablet can't be used to
 * skip someone's song; the host keeps those on the UncTunes dashboard, or
 * turns them on here with `show_controls: true`.
 *
 * Search and requests go through the integration's own HTTP views, so the
 * browser only ever holds a Home Assistant login — the venue token stays on
 * the HA server.
 *
 * No build step: plain custom elements, so the file the integration serves is
 * the file you read.
 */

const CARD_VERSION = '0.1.0';
const CARD_TAG = 'unctunes-card';
const EDITOR_TAG = 'unctunes-card-editor';

const DEFAULTS = {
  entity: '',
  title: null,
  show_search: true,
  show_queue: true,
  show_now_playing: true,
  show_controls: false,
  allow_priority: false,
  ask_name: false,
  requester: 'Jukebox',
  queue_limit: 10,
  idle_reset: 45,
};

const SEARCH_DEBOUNCE_MS = 350;
const NAME_STORAGE_KEY = 'unctunes-card-name';

function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmtMs(ms) {
  const total = Math.max(0, Math.floor((ms || 0) / 1000));
  const m = Math.floor(total / 60);
  const s = String(total % 60).padStart(2, '0');
  return `${m}:${s}`;
}

function readStoredName() {
  try { return localStorage.getItem(NAME_STORAGE_KEY) || ''; } catch (_) { return ''; }
}

function storeName(name) {
  try {
    if (name) localStorage.setItem(NAME_STORAGE_KEY, name);
    else localStorage.removeItem(NAME_STORAGE_KEY);
  } catch (_) { /* private mode etc. */ }
}

const STYLES = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .wrap { padding: 16px; display: flex; flex-direction: column; gap: 16px; }
  .header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .title { font-size: 1.15rem; font-weight: 600; margin: 0; }
  .pill { font-size: 0.75rem; font-weight: 600; letter-spacing: 0.02em; text-transform: uppercase;
    padding: 4px 10px; border-radius: 999px; background: var(--secondary-background-color, rgba(127,127,127,0.15));
    color: var(--secondary-text-color); white-space: nowrap; }
  .pill.playing { background: rgba(29, 185, 84, 0.18); color: #1db954; }
  .pill.paused { background: rgba(245, 158, 11, 0.18); color: #d97706; }
  .pill.off { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

  .now { display: grid; grid-template-columns: 96px 1fr; gap: 14px; align-items: center; }
  .art { width: 96px; height: 96px; border-radius: 10px; object-fit: cover;
    background: var(--secondary-background-color, rgba(127,127,127,0.15)); display: flex; align-items: center;
    justify-content: center; font-size: 2rem; }
  .now-meta { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  .now-title { font-weight: 600; font-size: 1.05rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .now-artist { color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .now-req { font-size: 0.85rem; color: var(--secondary-text-color); }
  .now-req b { color: var(--primary-text-color); font-weight: 600; }
  .progress { height: 4px; border-radius: 2px; background: var(--divider-color, rgba(127,127,127,0.3)); overflow: hidden; margin-top: 4px; }
  .progress > div { height: 100%; width: 0; background: var(--primary-color); transition: width 0.5s linear; }
  .times { display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .idle { color: var(--secondary-text-color); }

  .controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .controls input[type=range] { flex: 1; min-width: 120px; accent-color: var(--primary-color); }
  .icon-btn { width: 48px; height: 48px; border-radius: 50%; border: 1px solid var(--divider-color, rgba(127,127,127,0.3));
    background: var(--secondary-background-color, transparent); color: var(--primary-text-color); font-size: 1.2rem;
    cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
  .icon-btn:active { transform: scale(0.96); }

  .search { position: relative; }
  .search input[type=search], .search input[type=text] {
    width: 100%; box-sizing: border-box; font: inherit; font-size: 1.05rem; padding: 14px 16px;
    border-radius: 12px; border: 1.5px solid var(--divider-color, rgba(127,127,127,0.3));
    background: var(--secondary-background-color, transparent); color: var(--primary-text-color); outline: none; }
  .search input:focus { border-color: var(--primary-color); }
  .name-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
  .name-row input { font-size: 0.95rem !important; padding: 10px 12px !important; }
  .name-row label { font-size: 0.85rem; color: var(--secondary-text-color); white-space: nowrap; }
  .results { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
  .row { display: grid; grid-template-columns: 48px 1fr auto; gap: 10px; align-items: center; padding: 8px;
    border-radius: 10px; border: 1px solid var(--divider-color, rgba(127,127,127,0.25)); }
  .row .art { width: 48px; height: 48px; border-radius: 6px; font-size: 1.2rem; }
  .row-meta { min-width: 0; }
  .row-title { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row-sub { font-size: 0.85rem; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row-actions { display: flex; gap: 6px; }
  .add-btn { font: inherit; font-weight: 600; padding: 10px 14px; min-height: 44px; border-radius: 10px; cursor: pointer;
    border: none; background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .add-btn.secondary { background: transparent; color: var(--primary-color); border: 1.5px solid var(--primary-color); }
  .add-btn[disabled] { opacity: 0.5; cursor: default; }
  .hint { font-size: 0.85rem; color: var(--secondary-text-color); padding: 6px 2px; }
  .explicit { display: inline-block; font-size: 0.65rem; font-weight: 700; padding: 1px 4px; border-radius: 3px;
    background: var(--divider-color, rgba(127,127,127,0.3)); color: var(--secondary-text-color); margin-left: 6px; vertical-align: middle; }

  .queue h3 { margin: 0 0 8px; font-size: 0.9rem; font-weight: 600; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: 0.04em; }
  .queue .row { grid-template-columns: 28px 40px 1fr auto; }
  .queue .art { width: 40px; height: 40px; }
  .pos { font-weight: 700; color: var(--secondary-text-color); text-align: center; font-variant-numeric: tabular-nums; }
  .req { font-size: 0.8rem; color: var(--secondary-text-color); white-space: nowrap; }
  .flag { color: #f59e0b; margin-right: 4px; }

  .toast { position: absolute; left: 50%; bottom: 16px; transform: translateX(-50%) translateY(20px); opacity: 0;
    padding: 10px 16px; border-radius: 10px; background: var(--primary-color); color: var(--text-primary-color, #fff);
    font-weight: 600; pointer-events: none; transition: opacity 0.2s, transform 0.2s; max-width: calc(100% - 32px); box-sizing: border-box; }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
  .toast.error { background: #ef4444; }
  .closed { padding: 10px 12px; border-radius: 10px; background: rgba(245, 158, 11, 0.15); color: #d97706; font-size: 0.9rem; }
`;

class UncTunesCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass?.states || {}).find(
      (id) => id.startsWith('media_player.') && hass.states[id].attributes?.venue_slug
    );
    return { entity: entity || '', show_search: true, show_queue: true };
  }

  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass = null;
    this._built = false;
    this._lastKey = '';
    this._results = [];
    this._searchTimer = null;
    this._idleTimer = null;
    this._tick = null;
    this._toastTimer = null;
    this._busy = new Set();
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error('unctunes-card: set `entity` to the venue\'s media_player');
    this._config = { ...DEFAULTS, ...config };
    this._built = false;
    this._lastKey = '';
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 8; }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: 'auto' };
  }

  connectedCallback() {
    if (!this._tick) this._tick = setInterval(() => this._updateProgress(), 1000);
  }

  disconnectedCallback() {
    clearInterval(this._tick); this._tick = null;
    clearTimeout(this._searchTimer);
    clearTimeout(this._idleTimer);
  }

  // ── state helpers ─────────────────────────────────────────────────────────

  get _state() {
    return this._hass?.states?.[this._config?.entity] || null;
  }

  get _entryId() {
    return this._state?.attributes?.entry_id || null;
  }

  _statusPill(st) {
    if (!st || st.state === 'unavailable' || st.state === 'off') return ['off', st ? 'Offline' : 'Not found'];
    if (st.state === 'playing') return ['playing', 'Playing'];
    if (st.state === 'paused') return ['paused', 'Paused'];
    return ['idle', 'Idle'];
  }

  // ── rendering ─────────────────────────────────────────────────────────────

  _render() {
    if (!this._config || !this._hass) return;
    if (!this._built) this._build();
    const st = this._state;
    const a = st?.attributes || {};
    const key = JSON.stringify([st?.state, a.media_title, a.media_artist, a.entity_picture, a.requester, a.queue, a.queue_length,
      a.requests_open, a.volume_level, a.media_duration, a.media_position, a.media_position_updated_at, a.friendly_name]);
    if (key === this._lastKey) return;
    this._lastKey = key;
    this._renderHeader(st);
    if (this._config.show_now_playing) this._renderNow(st);
    if (this._config.show_queue) this._renderQueue(st);
    this._renderClosed(st);
  }

  _build() {
    const c = this._config;
    const root = this.shadowRoot;
    root.innerHTML = `
      <style>${STYLES}</style>
      <ha-card>
        <div class="wrap" style="position:relative;">
          <div class="header"><h2 class="title" id="title"></h2><span class="pill" id="pill"></span></div>
          ${c.show_now_playing ? '<div class="now" id="now"></div>' : ''}
          ${c.show_controls ? `<div class="controls" id="controls">
              <button class="icon-btn" id="btnPlayPause" title="Play / pause">⏯</button>
              <button class="icon-btn" id="btnSkip" title="Skip">⏭</button>
              <input type="range" id="volume" min="0" max="100" step="1" title="Volume">
            </div>` : ''}
          <div class="closed" id="closed" hidden></div>
          ${c.show_search ? `<div class="search" id="search">
              ${c.ask_name ? '<div class="name-row"><label for="who">Your name</label><input type="text" id="who" placeholder="optional" maxlength="40" autocomplete="off"></div>' : ''}
              <input type="search" id="q" placeholder="Search for a song or artist…" autocomplete="off" autocorrect="off" spellcheck="false" enterkeyhint="search">
              <div class="results" id="results"></div>
            </div>` : ''}
          ${c.show_queue ? '<div class="queue" id="queue"></div>' : ''}
          <div class="toast" id="toast"></div>
        </div>
      </ha-card>`;
    this._built = true;

    const q = root.getElementById('q');
    if (q) {
      q.addEventListener('input', () => this._onSearchInput(q.value));
      q.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); this._search(q.value); } });
    }
    const who = root.getElementById('who');
    if (who) {
      who.value = readStoredName();
      who.addEventListener('change', () => storeName(who.value.trim()));
    }
    const results = root.getElementById('results');
    if (results) {
      results.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-uri]');
        if (btn) this._request(btn.dataset.uri, btn.dataset.priority === '1', btn);
      });
    }
    if (c.show_controls) {
      root.getElementById('btnPlayPause').addEventListener('click', () => this._playPause());
      root.getElementById('btnSkip').addEventListener('click', () => this._call('media_player', 'media_next_track'));
      const vol = root.getElementById('volume');
      vol.addEventListener('change', () => this._call('media_player', 'volume_set', { volume_level: Number(vol.value) / 100 }));
    }
    root.querySelector('.wrap').addEventListener('pointerdown', () => this._touch());
  }

  _renderHeader(st) {
    const root = this.shadowRoot;
    const name = this._config.title ?? (st?.attributes?.friendly_name || 'UncTunes');
    root.getElementById('title').textContent = name;
    const [cls, label] = this._statusPill(st);
    const pill = root.getElementById('pill');
    pill.className = `pill ${cls}`;
    pill.textContent = label;
    const vol = root.getElementById('volume');
    if (vol && st?.attributes?.volume_level != null && document.activeElement !== vol) {
      vol.value = Math.round(st.attributes.volume_level * 100);
    }
    const pp = root.getElementById('btnPlayPause');
    if (pp) pp.textContent = st?.state === 'playing' ? '⏸' : '▶';
  }

  _renderNow(st) {
    const el = this.shadowRoot.getElementById('now');
    if (!el) return;
    const a = st?.attributes || {};
    if (!st || !a.media_title) {
      el.innerHTML = `<div class="art">🎵</div><div class="now-meta"><div class="now-title idle">Nothing playing</div>
        <div class="now-artist">${esc(a.queue_length ? 'Queue is ready — waiting for the host to start it' : 'Add a song to get things going')}</div></div>`;
      return;
    }
    const art = a.entity_picture ? `<img class="art" src="${esc(a.entity_picture)}" alt="">` : '<div class="art">🎵</div>';
    const req = a.is_autoplay ? 'Jukebox pick' : (a.requester ? `Requested by <b>${esc(a.requester)}</b>` : '');
    el.innerHTML = `${art}<div class="now-meta">
      <div class="now-title">${esc(a.media_title)}</div>
      <div class="now-artist">${esc(a.media_artist || '')}</div>
      ${req ? `<div class="now-req">${req}</div>` : ''}
      <div class="progress"><div id="bar"></div></div>
      <div class="times"><span id="tPos">0:00</span><span id="tDur">${fmtMs((a.media_duration || 0) * 1000)}</span></div>
    </div>`;
    this._updateProgress();
  }

  _updateProgress() {
    const st = this._state;
    const bar = this.shadowRoot?.getElementById('bar');
    if (!bar || !st) return;
    const a = st.attributes;
    const dur = (a.media_duration || 0) * 1000;
    let pos = (a.media_position || 0) * 1000;
    if (st.state === 'playing' && a.media_position_updated_at) {
      pos += Date.now() - new Date(a.media_position_updated_at).getTime();
    }
    pos = Math.min(pos, dur || pos);
    bar.style.width = dur ? `${(pos / dur) * 100}%` : '0%';
    const tPos = this.shadowRoot.getElementById('tPos');
    if (tPos) tPos.textContent = fmtMs(pos);
  }

  _renderQueue(st) {
    const el = this.shadowRoot.getElementById('queue');
    if (!el) return;
    const queue = st?.attributes?.queue || [];
    const total = st?.attributes?.queue_length || queue.length;
    const limit = Number(this._config.queue_limit) || 0;
    const shown = limit > 0 ? queue.slice(0, limit) : queue;
    if (!shown.length) {
      el.innerHTML = '<h3>Up next</h3><div class="hint">The queue is empty.</div>';
      return;
    }
    const rows = shown.map((q) => `
      <div class="row">
        <div class="pos">${q.position}</div>
        ${q.album_art ? `<img class="art" src="${esc(q.album_art)}" alt="">` : '<div class="art">🎵</div>'}
        <div class="row-meta">
          <div class="row-title">${q.priority ? '<span class="flag" title="Priority">⚡</span>' : ''}${esc(q.title)}</div>
          <div class="row-sub">${esc(q.artist || '')}</div>
        </div>
        <div class="req">${esc(q.autoplay ? 'Jukebox' : (q.requester || ''))}</div>
      </div>`).join('');
    const more = total > shown.length ? `<div class="hint">+${total - shown.length} more</div>` : '';
    el.innerHTML = `<h3>Up next · ${total}</h3>${rows}${more}`;
  }

  _renderClosed(st) {
    const el = this.shadowRoot.getElementById('closed');
    if (!el) return;
    const a = st?.attributes || {};
    const closed = a.requests_open === false;
    el.hidden = !closed;
    el.textContent = closed ? 'Requests are closed right now — the jukebox opens again during the venue\'s allowed hours.' : '';
  }

  // ── search & request ──────────────────────────────────────────────────────

  _onSearchInput(value) {
    clearTimeout(this._searchTimer);
    this._touch();
    if (!value.trim()) { this._results = []; this._renderResults(); return; }
    this._searchTimer = setTimeout(() => this._search(value), SEARCH_DEBOUNCE_MS);
  }

  async _search(value) {
    const q = value.trim();
    const entryId = this._entryId;
    if (!q || !entryId) return;
    const results = this.shadowRoot.getElementById('results');
    results.innerHTML = '<div class="hint">Searching…</div>';
    try {
      const data = await this._hass.callApi('GET', `unctunes/${entryId}/search?q=${encodeURIComponent(q)}`);
      if (this.shadowRoot.getElementById('q').value.trim() !== q) return; // stale
      this._results = data.tracks || [];
      this._renderResults(q);
    } catch (err) {
      results.innerHTML = `<div class="hint">${esc(this._errMsg(err, 'Search failed'))}</div>`;
    }
  }

  _renderResults(q = '') {
    const el = this.shadowRoot.getElementById('results');
    if (!el) return;
    if (!this._results.length) {
      el.innerHTML = q ? '<div class="hint">No matches.</div>' : '';
      return;
    }
    const priority = this._config.allow_priority;
    el.innerHTML = this._results.map((t) => `
      <div class="row">
        ${t.albumArt ? `<img class="art" src="${esc(t.albumArt)}" alt="">` : '<div class="art">🎵</div>'}
        <div class="row-meta">
          <div class="row-title">${esc(t.name)}${t.explicit ? '<span class="explicit">E</span>' : ''}</div>
          <div class="row-sub">${esc(t.artist)} · ${fmtMs(t.duration)}</div>
        </div>
        <div class="row-actions">
          <button class="add-btn" data-uri="${esc(t.uri)}" data-priority="0">+ Add</button>
          ${priority ? `<button class="add-btn secondary" data-uri="${esc(t.uri)}" data-priority="1" title="Play next">⚡</button>` : ''}
        </div>
      </div>`).join('');
  }

  async _request(uri, priority, btn) {
    const entryId = this._entryId;
    if (!entryId || this._busy.has(uri)) return;
    this._busy.add(uri);
    if (btn) btn.disabled = true;
    const who = this.shadowRoot.getElementById('who');
    const requester = (who?.value.trim()) || this._config.requester || 'Jukebox';
    try {
      const res = await this._hass.callApi('POST', `unctunes/${entryId}/request`, { uri, priority: !!priority, requester });
      const title = res?.entry?.track?.name || 'Song';
      const pos = res?.position;
      this._toast(pos ? `Added “${title}” — #${pos} in the queue` : `Added “${title}”`);
      setTimeout(() => this._resetSearch(), 1500);
    } catch (err) {
      this._toast(this._errMsg(err, 'Could not add that song'), true);
      if (btn) btn.disabled = false;
    } finally {
      this._busy.delete(uri);
    }
  }

  _resetSearch() {
    const q = this.shadowRoot.getElementById('q');
    if (q) q.value = '';
    this._results = [];
    this._renderResults();
  }

  _touch() {
    clearTimeout(this._idleTimer);
    const secs = Number(this._config.idle_reset) || 0;
    if (secs > 0) this._idleTimer = setTimeout(() => this._resetSearch(), secs * 1000);
  }

  // ── host controls ─────────────────────────────────────────────────────────

  async _call(domain, service, data = {}) {
    try {
      await this._hass.callService(domain, service, { entity_id: this._config.entity, ...data });
    } catch (err) {
      this._toast(this._errMsg(err, 'Action failed'), true);
    }
  }

  _playPause() {
    const st = this._state;
    this._call('media_player', st?.state === 'playing' ? 'media_pause' : 'media_play');
  }

  // ── misc ──────────────────────────────────────────────────────────────────

  _errMsg(err, fallback) {
    return err?.body?.message || err?.message || (typeof err === 'string' ? err : fallback);
  }

  _toast(msg, error = false) {
    const el = this.shadowRoot.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.className = `toast show${error ? ' error' : ''}`;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { el.className = 'toast'; }, 3200);
  }
}

// ── Editor ──────────────────────────────────────────────────────────────────

const EDITOR_SCHEMA = [
  { name: 'entity', required: true, selector: { entity: { domain: 'media_player', integration: 'unctunes' } } },
  { name: 'title', selector: { text: {} } },
  {
    type: 'grid',
    name: '',
    schema: [
      { name: 'show_now_playing', selector: { boolean: {} } },
      { name: 'show_search', selector: { boolean: {} } },
      { name: 'show_queue', selector: { boolean: {} } },
      { name: 'show_controls', selector: { boolean: {} } },
      { name: 'allow_priority', selector: { boolean: {} } },
      { name: 'ask_name', selector: { boolean: {} } },
    ],
  },
  { name: 'requester', selector: { text: {} } },
  { name: 'queue_limit', selector: { number: { min: 0, max: 50, mode: 'box' } } },
  { name: 'idle_reset', selector: { number: { min: 0, max: 600, mode: 'box', unit_of_measurement: 's' } } },
];

const EDITOR_LABELS = {
  entity: 'Venue (media player)',
  title: 'Title (defaults to the venue name)',
  show_now_playing: 'Show now playing',
  show_search: 'Show song search',
  show_queue: 'Show the queue',
  show_controls: 'Show host controls (pause, skip, volume)',
  allow_priority: 'Allow “play next” requests',
  ask_name: 'Ask guests for their name',
  requester: 'Default requester name',
  queue_limit: 'Queue rows to show (0 = all)',
  idle_reset: 'Clear the search after idle seconds (0 = never)',
};

async function ensureHaForm() {
  if (customElements.get('ha-form')) return;
  try {
    const helpers = await window.loadCardHelpers?.();
    const el = helpers?.createCardElement({ type: 'entities', entities: [] });
    await el?.constructor?.getConfigElement?.();
  } catch (_) { /* fall back to a plain YAML editor */ }
}

class UncTunesCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...DEFAULTS, ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  async _render() {
    await ensureHaForm();
    if (!this._form) {
      this._form = document.createElement('ha-form');
      this._form.computeLabel = (s) => EDITOR_LABELS[s.name] || s.name;
      this._form.addEventListener('value-changed', (e) => {
        const config = { type: `custom:${CARD_TAG}`, ...e.detail.value };
        this._config = config;
        this.dispatchEvent(new CustomEvent('config-changed', { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = EDITOR_SCHEMA;
    this._form.data = this._config;
  }
}

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, UncTunesCard);
if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, UncTunesCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: 'UncTunes Jukebox',
    description: 'Walk-up song requests, now playing, and the queue for an UncTunes venue.',
    preview: true,
    documentationURL: 'https://github.com/cladkins/unctunes-ha',
  });
}

console.info(`%c UNCTUNES-CARD %c ${CARD_VERSION} `, 'color:#fff;background:#1db954;font-weight:700', 'color:#1db954;background:#0d0d14');

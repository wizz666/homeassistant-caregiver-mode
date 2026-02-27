/**
 * caregiver-card.js
 * Custom Lovelace card for Caregiver Mode integration
 * https://github.com/wizz666/homeassistant-caregiver-mode
 */

const STATUS_COLORS = {
  active:   { bg: '#E8F5E9', border: '#4CAF50', badge: '#4CAF50', text: '#fff' },
  inactive: { bg: '#FFF8E1', border: '#FF9800', badge: '#FF9800', text: '#fff' },
  alert:    { bg: '#FFEBEE', border: '#F44336', badge: '#F44336', text: '#fff' },
  unknown:  { bg: 'var(--card-background-color)', border: '#9E9E9E', badge: '#9E9E9E', text: '#fff' },
};

const STATUS_LABELS = {
  active:   'Aktiv',
  inactive: 'Inaktiv',
  alert:    'LARM',
  unknown:  'Okänd',
};

const STATUS_ICONS = {
  active:   'mdi:check-circle',
  inactive: 'mdi:clock-alert-outline',
  alert:    'mdi:alert-circle',
  unknown:  'mdi:help-circle-outline',
};

function relativeTime(isoString) {
  if (!isoString || isoString === 'unknown' || isoString === 'unavailable') return '—';
  const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
  if (diff < 60)   return 'nyss';
  if (diff < 3600) return `${Math.floor(diff / 60)} min sedan`;
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  if (h < 24) return m > 0 ? `${h} tim ${m} min sedan` : `${h} tim sedan`;
  return `${Math.floor(h / 24)} dagar sedan`;
}

class CaregiverCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._refreshTimer = null;
  }

  setConfig(config) {
    if (!config.entity_prefix) {
      throw new Error('Caregiver Card: entity_prefix krävs (t.ex. "farmor")');
    }
    this._config = config;
    const slug = config.entity_prefix.toLowerCase().replace(/\s+/g, '_');
    this._entities = {
      status:    `sensor.caregiver_${slug}_status`,
      last_seen: `sensor.caregiver_${slug}_last_seen`,
      last_room: `sensor.caregiver_${slug}_last_room`,
      alert:     `binary_sensor.caregiver_${slug}_alert`,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    // Auto-refresh relative time every 30s
    if (!this._refreshTimer) {
      this._refreshTimer = setInterval(() => this._render(), 30000);
    }
  }

  disconnectedCallback() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  _getState(entityId) {
    return this._hass?.states?.[entityId];
  }

  _render() {
    if (!this._hass || !this._config) return;

    const statusEnt   = this._getState(this._entities.status);
    const lastSeenEnt = this._getState(this._entities.last_seen);
    const lastRoomEnt = this._getState(this._entities.last_room);
    const alertEnt    = this._getState(this._entities.alert);

    const status      = statusEnt?.state ?? 'unknown';
    const lastSeen    = lastSeenEnt?.state;
    const lastRoom    = lastRoomEnt?.state;
    const alertActive = alertEnt?.state === 'on';
    const personName  = this._config.name || this._config.entity_prefix;

    const color  = STATUS_COLORS[status] ?? STATUS_COLORS.unknown;
    const label  = STATUS_LABELS[status] ?? status;
    const relTs  = relativeTime(lastSeen);
    const room   = (lastRoom && lastRoom !== 'unknown' && lastRoom !== 'unavailable') ? lastRoom : '—';

    const pulseStyle = alertActive
      ? '@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.65} } .header{animation:pulse 1.4s ease-in-out infinite;}'
      : '';

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }

        .card {
          background: var(--card-background-color, #fff);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.12));
          overflow: hidden;
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }

        ${pulseStyle}

        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 14px 16px;
          background: ${color.bg};
          border-left: 5px solid ${color.border};
        }

        .person {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .person-icon {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          background: ${color.border};
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }

        .person-icon span {
          font-size: 1.3rem;
          line-height: 1;
        }

        .person-name {
          font-size: 1.1rem;
          font-weight: 600;
          color: var(--primary-text-color);
        }

        .badge {
          background: ${color.badge};
          color: ${color.text};
          border-radius: 20px;
          padding: 4px 14px;
          font-size: 0.78rem;
          font-weight: 700;
          letter-spacing: .8px;
          text-transform: uppercase;
          white-space: nowrap;
        }

        .body {
          padding: 12px 16px 14px;
        }

        .row {
          display: flex;
          align-items: center;
          padding: 5px 0;
          font-size: 0.92rem;
          border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.08));
        }

        .row:last-child {
          border-bottom: none;
          padding-bottom: 0;
        }

        .row-label {
          color: var(--secondary-text-color);
          flex: 1;
        }

        .row-value {
          font-weight: 500;
          color: var(--primary-text-color);
          text-align: right;
        }

        .alert-strip {
          background: #F44336;
          color: #fff;
          text-align: center;
          padding: 5px 8px;
          font-size: 0.8rem;
          font-weight: 700;
          letter-spacing: 1px;
          display: ${alertActive ? 'block' : 'none'};
        }
      </style>

      <div class="card">
        ${alertActive ? '<div class="alert-strip">⚠ LARM AKTIVT — KONTAKTA NU</div>' : ''}
        <div class="header">
          <div class="person">
            <div class="person-icon">
              <span>${alertActive ? '⚠️' : '🧓'}</span>
            </div>
            <span class="person-name">${personName}</span>
          </div>
          <span class="badge">${label}</span>
        </div>
        <div class="body">
          <div class="row">
            <span class="row-label">Senast sedd</span>
            <span class="row-value">${relTs}</span>
          </div>
          <div class="row">
            <span class="row-label">Senaste rum</span>
            <span class="row-value">${room}</span>
          </div>
        </div>
      </div>
    `;
  }

  getCardSize() { return 2; }

  static getStubConfig() {
    return { entity_prefix: 'farmor', name: 'Farmor' };
  }
}

customElements.define('caregiver-card', CaregiverCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'caregiver-card',
  name: 'Caregiver Card',
  description: 'Statusvisning för Caregiver Mode – visar aktivitet, senaste rum och larmstatus.',
  preview: true,
  documentationURL: 'https://github.com/wizz666/homeassistant-caregiver-mode',
});

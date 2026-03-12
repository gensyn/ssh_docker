// SSH Docker Card – Lovelace card for a single Docker container sensor.
class SshDockerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entity = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You need to define an entity");
    }
    this.config = config;
  }

  _stateColor(state) {
    switch (state) {
      case "running":    return "#27ae60";
      case "exited":     return "#e74c3c";
      case "paused":     return "#f39c12";
      case "restarting": return "#3498db";
      case "dead":       return "#8e44ad";
      default:           return "#95a5a6";
    }
  }

  _render() {
    if (!this._hass || !this.config) return;

    const entityId = this.config.entity;
    const entity = this._hass.states[entityId];
    const attrs = (entity && entity.attributes) || {};
    const state = (entity && entity.state) || "unavailable";
    const name = attrs.friendly_name || entityId;
    const image = attrs.image || "-";
    const created = attrs.created ? attrs.created.slice(0, 10) : "-";
    const host = attrs.host || "-";
    const updateBadge = attrs.update_available
      ? `<span class="update-badge">⬆ Update available</span>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { color: var(--primary-text-color); }
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 16px;
          font-size: 1rem;
          font-weight: 600;
          border-bottom: 1px solid rgba(0,0,0,0.1);
          background: ${this._stateColor(state)};
          color: white;
          border-radius: 8px 8px 0 0;
        }
        .badge {
          display: inline-block;
          padding: 2px 10px;
          border-radius: 12px;
          font-size: 0.78em;
          background: rgba(255,255,255,0.3);
          text-transform: capitalize;
        }
        .card-content {
          padding: 10px 16px 14px;
        }
        table { width: 100%; border-collapse: collapse; }
        td { padding: 4px 0; font-size: 0.875em; }
        td:last-child { text-align: right; color: var(--secondary-text-color); }
        .update-badge {
          background: #e67e22;
          color: white;
          padding: 2px 8px;
          border-radius: 10px;
          font-size: 0.78em;
        }
        .image { font-family: monospace; font-size: 0.8em; }
      </style>
      <ha-card>
        <div class="card-header">
          <span>${name}</span>
          <span class="badge">${state}</span>
        </div>
        <div class="card-content">
          <table>
            <tr><td>Host</td><td>${host}</td></tr>
            <tr><td>Image</td><td class="image">${image}</td></tr>
            <tr><td>Created</td><td>${created}</td></tr>
            ${attrs.update_available ? `<tr><td colspan="2">${updateBadge}</td></tr>` : ""}
          </table>
        </div>
      </ha-card>
    `;
  }

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return { rows: 3, columns: 6, min_rows: 2 };
  }
}

customElements.define("ssh-docker-card", SshDockerCard);

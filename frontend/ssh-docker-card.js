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
      case "created":    return "#16a085";
      case "removing":   return "#c0392b";
      case "stopping":   return "#e67e22";
      case "creating":   return "#2980b9";
      default:           return "#95a5a6";
    }
  }

  _handleAction(action, entityId) {
    if (!this._hass) return;
    if (action === "refresh") {
      this._hass.callService("homeassistant", "update_entity", { entity_id: entityId });
    } else {
      this._hass.callService("ssh_docker", action, { entity_id: entityId });
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

    // Conditional button visibility — same logic as the panel.
    const showCreate   = attrs.docker_create_available === true;
    const createLabel  = state !== "unavailable"
      ? (attrs.update_available && state === "running" ? "⬆ Update" : "✚ Recreate")
      : "✚ Create";
    const stoppedStates = ["exited", "created", "dead", "paused"];
    const showRestart  = state === "running";
    const showStart    = stoppedStates.includes(state);
    const showStop     = state === "running";
    const showRemove   = state !== "unavailable";

    const actionButtons = [
      showCreate  ? `<button class="action-btn create-btn"  data-action="create"  data-entity="${entityId}">${createLabel}</button>` : "",
      showRestart ? `<button class="action-btn restart-btn" data-action="restart" data-entity="${entityId}">↺ Restart</button>` : "",
      showStart   ? `<button class="action-btn restart-btn" data-action="restart" data-entity="${entityId}">▶ Start</button>`   : "",
      showStop    ? `<button class="action-btn stop-btn"    data-action="stop"    data-entity="${entityId}">■ Stop</button>`    : "",
      showRemove  ? `<button class="action-btn remove-btn"  data-action="remove"  data-entity="${entityId}">🗑 Remove</button>`  : "",
      `<button class="action-btn refresh-btn" data-action="refresh" data-entity="${entityId}">↻ Refresh</button>`,
    ].filter(Boolean).join("");

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
          flex-shrink: 0;
        }
        .card-content {
          padding: 10px 16px 14px;
        }
        table { width: 100%; border-collapse: collapse; }
        td { padding: 4px 0; font-size: 0.875em; color: var(--primary-text-color); }
        td:last-child { text-align: right; color: var(--secondary-text-color); }
        .update-badge {
          background: #e67e22;
          color: white;
          padding: 2px 8px;
          border-radius: 10px;
          font-size: 0.78em;
          font-weight: 500;
        }
        .image { font-family: monospace; font-size: 0.8em; }
        .action-buttons {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 10px;
          padding-top: 8px;
          border-top: 1px solid var(--divider-color, #e0e0e0);
        }
        .action-btn {
          padding: 4px 10px;
          border: none;
          border-radius: 12px;
          cursor: pointer;
          font-size: 0.78em;
          font-family: inherit;
          font-weight: 500;
          transition: opacity 0.2s;
          color: white;
        }
        .action-btn:hover { opacity: 0.85; }
        .create-btn  { background: #16a085; }
        .restart-btn { background: #3498db; }
        .stop-btn    { background: #e67e22; }
        .remove-btn  { background: #e74c3c; }
        .refresh-btn { background: #7f8c8d; }
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
          <div class="action-buttons">${actionButtons}</div>
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".action-btn").forEach((btn) => {
      btn.addEventListener("click", () =>
        this._handleAction(btn.dataset.action, btn.dataset.entity)
      );
    });
  }

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return { rows: 3, columns: 6, min_rows: 2 };
  }
}

customElements.define("ssh-docker-card", SshDockerCard);

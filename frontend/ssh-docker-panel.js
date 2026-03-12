// SSH Docker Panel – sidebar panel and Lovelace card that lists all docker containers grouped by host.
class SshDockerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _getSshDockerEntities() {
    if (!this._hass) return [];
    return Object.values(this._hass.states).filter(
      (entity) => entity.entity_id.startsWith("sensor.ssh_docker_")
    );
  }

  _groupByHost(entities) {
    const groups = {};
    for (const entity of entities) {
      const host = (entity.attributes && entity.attributes.host) ? entity.attributes.host : "Unknown Host";
      if (!groups[host]) groups[host] = [];
      groups[host].push(entity);
    }
    return groups;
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
    const entities = this._getSshDockerEntities();
    const groups = this._groupByHost(entities);
    let hostsHtml = "";

    if (Object.keys(groups).length === 0) {
      hostsHtml = `<p class="empty">No Docker containers configured yet.</p>`;
    } else {
      for (const [host, hostEntities] of Object.entries(groups)) {
        let rows = "";
        for (const entity of hostEntities) {
          const attrs = entity.attributes || {};
          const name = attrs.friendly_name || entity.entity_id;
          const state = entity.state || "unavailable";
          const image = attrs.image || "-";
          const created = attrs.created ? attrs.created.slice(0, 10) : "-";
          const updateBadge = attrs.update_available
            ? `<span class="update-badge">⬆ Update available</span>`
            : "";
          rows += `
            <tr>
              <td class="name">${name}</td>
              <td><span class="badge" style="background:${this._stateColor(state)}">${state}</span></td>
              <td class="image">${image}</td>
              <td>${created}</td>
              <td>${updateBadge}</td>
            </tr>`;
        }
        hostsHtml += `
          <div class="host-section">
            <h3 class="host-title">�� ${host}</h3>
            <table>
              <thead>
                <tr>
                  <th>Container</th>
                  <th>State</th>
                  <th>Image</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>`;
      }
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          background: var(--primary-background-color, #fafafa);
          overflow-y: auto;
        }
        .panel-content {
          max-width: 1200px;
          margin: 0 auto;
          padding: 24px 16px;
        }
        .panel-header {
          font-size: 1.5em;
          font-weight: bold;
          color: var(--primary-text-color);
          margin: 0 0 24px;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .host-section {
          background: var(--card-background-color, #fff);
          border-radius: 8px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.1));
          margin-bottom: 24px;
          overflow: hidden;
        }
        .host-title {
          margin: 0;
          padding: 14px 16px;
          font-size: 1em;
          font-weight: 600;
          color: var(--primary-text-color);
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          background: var(--secondary-background-color, #f5f5f5);
        }
        table { width: 100%; border-collapse: collapse; }
        th {
          text-align: left;
          padding: 10px 16px;
          font-size: 0.82em;
          color: var(--secondary-text-color);
          font-weight: 500;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        td { padding: 10px 16px; font-size: 0.9em; vertical-align: middle; }
        tr:not(:last-child) td { border-bottom: 1px solid var(--divider-color, #e0e0e0); }
        tr:hover td { background: var(--secondary-background-color, #f5f5f5); }
        .badge {
          display: inline-block;
          padding: 3px 10px;
          border-radius: 12px;
          font-size: 0.78em;
          color: white;
          font-weight: 500;
          text-transform: capitalize;
        }
        .name { font-weight: 500; }
        .image { font-family: monospace; font-size: 0.8em; color: var(--secondary-text-color); }
        .update-badge {
          background: #e67e22;
          color: white;
          padding: 3px 8px;
          border-radius: 10px;
          font-size: 0.78em;
          font-weight: 500;
        }
        .empty {
          color: var(--secondary-text-color);
          text-align: center;
          padding: 48px 0;
          font-style: italic;
        }
      </style>
      <div class="panel-content">
        <h1 class="panel-header">🐳 Docker Services</h1>
        ${hostsHtml}
      </div>
    `;
  }

  // --- Lovelace card compatibility ---
  setConfig(config) {
    this.config = config || {};
  }

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return { rows: 3, columns: 12, min_rows: 2 };
  }
}

customElements.define("ssh-docker-panel", SshDockerPanel);

// SSH Docker Panel – custom Lovelace card that lists all docker containers grouped by host.
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
            <h3 class="host-title">🖥 ${host}</h3>
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
        :host { display: block; }
        ha-card { padding: 0; }
        .card-header {
          padding: 16px 16px 8px;
          font-size: 1.3em;
          font-weight: bold;
          color: var(--primary-text-color);
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .card-content { padding: 0 16px 16px; }
        .host-section { margin-bottom: 24px; }
        .host-title {
          margin: 12px 0 8px;
          font-size: 1em;
          color: var(--secondary-text-color);
          border-bottom: 1px solid var(--divider-color);
          padding-bottom: 4px;
        }
        table { width: 100%; border-collapse: collapse; }
        th {
          text-align: left;
          padding: 6px 8px;
          font-size: 0.82em;
          color: var(--secondary-text-color);
          font-weight: 500;
        }
        td { padding: 7px 8px; font-size: 0.9em; vertical-align: middle; }
        tr:hover td { background: var(--secondary-background-color); }
        .badge {
          display: inline-block;
          padding: 2px 10px;
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
          padding: 2px 8px;
          border-radius: 10px;
          font-size: 0.78em;
          font-weight: 500;
        }
        .empty {
          color: var(--secondary-text-color);
          text-align: center;
          padding: 32px 0;
          font-style: italic;
        }
      </style>
      <ha-card>
        <div class="card-header">🐳 Docker Services</div>
        <div class="card-content">${hostsHtml}</div>
      </ha-card>
    `;
  }

  setConfig(config) {
    this.config = config || {};
  }

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return {
      rows: 3,
      columns: 12,
      min_rows: 2,
    };
  }
}

customElements.define("ssh-docker-panel", SshDockerPanel);

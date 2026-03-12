// SSH Docker Panel – sidebar panel that lists all docker containers grouped by host.

/** Strip the " State" suffix that HA appends via the entity naming convention. */
function _stripStateSuffix(name) {
  const suffix = " State";
  return name.endsWith(suffix) ? name.slice(0, -suffix.length) : name;
}

class SshDockerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._filter = "all";
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  set panel(panel) {
    this._panel = panel;
  }

  _getAllContainers() {
    if (!this._hass) return [];
    const containers = Object.values(this._hass.states).filter((entity) =>
      entity.entity_id.startsWith("sensor.ssh_docker_")
    );
    // Always sort alphabetically by display name (stripping the " State" suffix).
    return containers.sort((a, b) => {
      const nameA = _stripStateSuffix((a.attributes && a.attributes.friendly_name) || a.entity_id);
      const nameB = _stripStateSuffix((b.attributes && b.attributes.friendly_name) || b.entity_id);
      return nameA.localeCompare(nameB);
    });
  }

  _getFilteredContainers() {
    const containers = this._getAllContainers();
    if (this._filter === "all") return containers;
    if (this._filter === "update_available") {
      return containers.filter((c) => c.attributes && c.attributes.update_available === true);
    }
    return containers.filter((c) => c.state === this._filter);
  }

  _setFilter(filter) {
    this._filter = filter;
    this._render();
  }

  _groupByHost(containers) {
    const groups = {};
    for (const entity of containers) {
      const host =
        entity.attributes && entity.attributes.host
          ? entity.attributes.host
          : "Unknown Host";
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
      case "created":    return "#16a085";
      case "removing":   return "#c0392b";
      case "stopping":   return "#e67e22";
      case "creating":   return "#2980b9";
      default:           return "#95a5a6";
    }
  }

  _renderContainerCard(entity) {
    const attrs = entity.attributes || {};
    const name = _stripStateSuffix(attrs.friendly_name || entity.entity_id);
    const state = entity.state || "unavailable";
    const image = attrs.image || "-";
    const created = attrs.created ? attrs.created.slice(0, 10) : "-";
    const updateBadge = attrs.update_available
      ? `<span class="update-badge">⬆ Update available</span>`
      : "";
    const entityId = entity.entity_id;

    // Conditional button visibility per the requirements.
    // Create/Recreate: only if docker_create is available; label changes based on container state.
    const showCreate   = attrs.docker_create_available === true;
    const createLabel  = state !== "unavailable" ? "✚ Recreate" : "✚ Create";
    // Start/Restart: show for running (Restart) or stopped states (Start).
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

    return `
      <div class="container-card">
        <div class="container-card-header" style="background:${this._stateColor(state)}">
          <span class="container-name">${name}</span>
          <span class="state-badge">${state}</span>
        </div>
        <div class="container-card-content">
          <table>
            <tr><td>Image</td><td class="image-cell">${image}</td></tr>
            <tr><td>Created</td><td>${created}</td></tr>
            ${attrs.update_available ? `<tr><td colspan="2">${updateBadge}</td></tr>` : ""}
          </table>
          ${actionButtons ? `<div class="action-buttons">${actionButtons}</div>` : ""}
        </div>
      </div>
    `;
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
    if (!this._hass) return;

    const allContainers = this._getAllContainers();
    const filteredContainers = this._getFilteredContainers();

    const states = ["running", "exited", "paused", "restarting", "dead", "unavailable"];
    const counts = { all: allContainers.length };
    for (const s of states) {
      counts[s] = allContainers.filter((c) => c.state === s).length;
    }
    counts["update_available"] = allContainers.filter(
      (c) => c.attributes && c.attributes.update_available === true
    ).length;

    const filterKeys = ["all", ...states, "update_available"];
    const filterLabels = { update_available: "⬆ updates" };
    const filterButtons = filterKeys
      .filter((f) => f === "all" || counts[f] > 0)
      .map(
        (f) =>
          `<button class="filter-btn${this._filter === f ? " active" : ""}"
                   data-filter="${f}">
            ${filterLabels[f] || (f === "all" ? "All" : f)} (${counts[f]})
           </button>`
      )
      .join("");

    const groups = this._groupByHost(filteredContainers);
    let hostsHtml = "";

    if (Object.keys(groups).length === 0) {
      hostsHtml = `<p class="no-containers">No Docker containers found.</p>`;
    } else {
      for (const [host, hostContainers] of Object.entries(groups)) {
        const cards = hostContainers
          .map((c) => this._renderContainerCard(c))
          .join("");
        hostsHtml += `
          <div class="host-section">
            <h2 class="host-title">🖥 ${host}</h2>
            <div class="container-grid">${cards}</div>
          </div>
        `;
      }
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
        }
        h1 {
          margin: 0 0 16px 0;
          font-size: 1.5rem;
          color: var(--primary-text-color, #212121);
        }
        .filters {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 16px;
        }
        .filter-btn {
          padding: 6px 14px;
          border: 2px solid var(--primary-color, #03a9f4);
          background: transparent;
          color: var(--primary-color, #03a9f4);
          border-radius: 20px;
          cursor: pointer;
          font-size: 0.875rem;
          font-family: inherit;
          transition: background 0.2s, color 0.2s;
        }
        .filter-btn.active {
          background: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, white);
        }
        .filter-btn:hover:not(.active) {
          background: rgba(3, 169, 244, 0.1);
        }
        .filter-btn[data-filter="update_available"] {
          border-color: #e67e22;
          color: #e67e22;
        }
        .filter-btn[data-filter="update_available"].active {
          background: #e67e22;
          color: white;
        }
        .filter-btn[data-filter="update_available"]:hover:not(.active) {
          background: rgba(230, 126, 34, 0.1);
        }
        .host-section {
          margin-bottom: 24px;
        }
        .host-title {
          margin: 0 0 12px 0;
          font-size: 1.1rem;
          color: var(--secondary-text-color, #727272);
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          padding-bottom: 6px;
        }
        .container-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
          gap: 16px;
        }
        .container-card {
          border-radius: 8px;
          overflow: hidden;
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,0.2));
          background: var(--card-background-color, white);
        }
        .container-card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 16px;
          color: white;
        }
        .container-name {
          font-size: 1rem;
          font-weight: 600;
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          margin-right: 8px;
        }
        .state-badge {
          background: rgba(255,255,255,0.3);
          padding: 2px 10px;
          border-radius: 12px;
          font-size: 0.78em;
          flex-shrink: 0;
          text-transform: capitalize;
        }
        .container-card-content {
          padding: 8px 16px 12px;
        }
        table { width: 100%; border-collapse: collapse; }
        td { padding: 4px 0; font-size: 0.875rem; color: var(--primary-text-color, #212121); }
        td:last-child {
          text-align: right;
          color: var(--secondary-text-color, #727272);
        }
        .image-cell { font-family: monospace; font-size: 0.8em; }
        .update-badge {
          background: #e67e22;
          color: white;
          padding: 2px 8px;
          border-radius: 10px;
          font-size: 0.78em;
          font-weight: 500;
        }
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
        .no-containers {
          color: var(--secondary-text-color, #727272);
          font-style: italic;
        }
      </style>
      <h1>SSH Docker</h1>
      <div class="filters">${filterButtons}</div>
      ${hostsHtml}
    `;

    this.shadowRoot.querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => this._setFilter(btn.dataset.filter));
    });

    this.shadowRoot.querySelectorAll(".action-btn").forEach((btn) => {
      btn.addEventListener("click", () =>
        this._handleAction(btn.dataset.action, btn.dataset.entity)
      );
    });
  }
}

customElements.define("ssh-docker-panel", SshDockerPanel);

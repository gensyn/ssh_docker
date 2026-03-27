// SSH Docker Panel – sidebar panel that lists all docker containers grouped by host.

class SshDockerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._filter = "all";
    this._hostFilter = "all";
    this._narrow = false;
    this._lastSnapshot = null;
    this._collapsedHosts = new Set();
    this._failedEntries = [];
    this._isFetchingFailedEntries = false;
  }

  set hass(hass) {
    this._hass = hass;
    // Only re-render when SSH Docker entity states/attributes actually changed.
    const snapshot = this._sshDockerSnapshot(hass);
    if (snapshot === this._lastSnapshot) return;
    this._lastSnapshot = snapshot;
    this._render();
  }

  set narrow(value) {
    this._narrow = value;
    this._render();
  }

  set header(value) {
    this._header = value;
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    // Re-render when the browser tab regains focus (handles blank panel after tab switch).
    this._visibilityHandler = () => {
      if (document.visibilityState === "visible" && this._hass) {
        this._lastSnapshot = null; // force re-render
        this._render();
        this._refreshFailedEntries();
      }
    };
    document.addEventListener("visibilitychange", this._visibilityHandler);

    // Handle page restore from browser BFCache (back/forward cache) or tab un-suspension.
    // Firefox fires pageshow with event.persisted=true when a frozen page is restored.
    this._pageshowHandler = (e) => {
      if (e.persisted && this._hass) {
        this._lastSnapshot = null;
        this._render();
        this._refreshFailedEntries();
      }
    };
    window.addEventListener("pageshow", this._pageshowHandler);

    // Last-resort fallback: if the shadow DOM is empty when the window regains focus,
    // force a re-render. This covers Linux WMs / Firefox builds where visibilitychange
    // or pageshow may not fire reliably for browser-tab switches.
    this._focusHandler = () => {
      if (this._hass && !this.shadowRoot.querySelector(".content")) {
        this._lastSnapshot = null;
        this._render();
      }
    };
    window.addEventListener("focus", this._focusHandler);

    // If hass is already set (panel re-attached by HA router navigation), force a fresh
    // render instead of relying on the snapshot diff which may incorrectly skip it.
    if (this._hass) {
      this._lastSnapshot = null;
    }
    this._render();
    this._refreshFailedEntries();
  }

  disconnectedCallback() {
    if (this._visibilityHandler) {
      document.removeEventListener("visibilitychange", this._visibilityHandler);
      this._visibilityHandler = null;
    }
    if (this._pageshowHandler) {
      window.removeEventListener("pageshow", this._pageshowHandler);
      this._pageshowHandler = null;
    }
    if (this._focusHandler) {
      window.removeEventListener("focus", this._focusHandler);
      this._focusHandler = null;
    }
  }

  // Returns a compact string snapshot of all SSH Docker sensor states + attributes.
  // Used to skip re-renders when no Docker-domain entity changed.
  _sshDockerSnapshot(hass) {
    if (!hass) return "";
    return Object.entries(hass.states)
      .filter(([id]) => id.startsWith("sensor.ssh_docker_"))
      .map(([id, e]) => `${id}=${e.state}|${JSON.stringify(e.attributes)}`)
      .join(";");
  }

  // Fetches SSH Docker config entries and updates _failedEntries with those that
  // have a setup_error state.  A simple guard prevents concurrent fetches.
  // Re-renders the panel when the failed entries list changes.
  async _refreshFailedEntries() {
    if (!this._hass || this._isFetchingFailedEntries) return;
    this._isFetchingFailedEntries = true;
    try {
      const entries = await this._hass.callApi("GET", "config/config_entries/entry?domain=ssh_docker");
      const failed = (entries || []).filter((e) => e.state === "setup_error");
      const changed = JSON.stringify(failed) !== JSON.stringify(this._failedEntries);
      this._failedEntries = failed;
      if (changed) this._render();
    } catch (_err) {
      // Silently ignore – the failed-entries section is non-critical.
    } finally {
      this._isFetchingFailedEntries = false;
    }
  }

  // Returns the HTML for the "failed entries" section shown above the container grid.
  _renderFailedSection() {
    if (!this._failedEntries || this._failedEntries.length === 0) return "";

    const cards = this._failedEntries.map((entry) => {
      // Host is sourced from entry.options returned by the config entries API.
      const host = (entry.options && entry.options.host) || "";
      const hostHtml = host
        ? `<div class="setup-failed-host">${this._t("host_label")}: ${host}</div>`
        : "";
      return `
      <div class="container-card">
        <div class="container-card-header" style="background:#c0392b">
          <span class="container-name">${entry.title}</span>
          <span class="state-badge">${this._t("setup_failed_badge")}</span>
        </div>
        <div class="container-card-content">
          ${hostHtml}
          <p class="setup-failed-hint">${this._t("setup_failed_hint")}</p>
          <div class="action-buttons">
            <button class="action-btn open-settings-btn"
                    data-href="/config/integrations/integration/ssh_docker">
              ${this._t("btn_open_settings")}
            </button>
          </div>
        </div>
      </div>
    `;
    }).join("");
    return `
      <div class="failed-entries-section">
        <h3 class="failed-section-title">⚠ ${this._t("setup_failed_section")}</h3>
        <div class="container-grid">${cards}</div>
      </div>
    `;
  }

  // Returns a set of entity_ids that belong to failed config entries.
  // Uses three strategies so that entities are always excluded from the regular grid,
  // even when attributes are empty (restored unavailable entity) or hass.entities is
  // not yet populated.
  _getFailedEntityIds() {
    if (!this._hass || !this._failedEntries.length) return new Set();
    const failedEntryIds = new Set(this._failedEntries.map((e) => e.entry_id).filter(Boolean));
    const result = new Set();

    // Strategy 1: entity registry — add entity_ids directly by config_entry_id.
    // Does NOT require the entity to have a state in hass.states, so it works even
    // for restored-but-never-loaded entities that have no attributes.
    if (this._hass.entities) {
      for (const [entityId, info] of Object.entries(this._hass.entities)) {
        if (entityId.startsWith("sensor.ssh_docker_") && failedEntryIds.has(info.config_entry_id)) {
          result.add(entityId);
        }
      }
    }

    // Strategies 2 & 3: iterate hass.states once as fallback when hass.entities is
    // not available or the entity has no state yet.
    const derivedIds = new Set(
      this._failedEntries
        .map((e) => e.title)
        .filter(Boolean)
        .map((t) => "sensor.ssh_docker_" + this._slugify(t))
    );
    for (const state of Object.values(this._hass.states)) {
      if (!state.entity_id.startsWith("sensor.ssh_docker_")) continue;
      // Strategy 2: name-attribute match (works when entity has populated attributes).
      if (state.attributes && state.attributes.name) {
        for (const entry of this._failedEntries) {
          if (entry.title && state.attributes.name === entry.title) {
            result.add(state.entity_id);
            break;
          }
        }
      }
      // Strategy 3: derived entity_id match (covers unavailable entities with empty
      // attributes, where the entity_id was generated from the entry title by HA's slugify).
      if (derivedIds.has(state.entity_id)) result.add(state.entity_id);
    }

    return result;
  }

  // Mirrors HA's Python slugify: lowercases the text, replaces every run of
  // non-alphanumeric characters with a single underscore, and strips leading/trailing
  // underscores.  Non-ASCII characters are treated as non-alphanumeric (become "_").
  // An all-non-alphanumeric input (e.g. "!!!") produces an empty string.
  _slugify(text) {
    return String(text).toLowerCase().replace(/[^a-z0-9]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
  }

  _t(key) {
    return (this._hass && this._hass.localize(`component.ssh_docker.entity.ui.${key}.name`)) || key;
  }

  _tState(state) {
    return (this._hass && this._hass.localize(`component.ssh_docker.entity.sensor.state.state.${state}`)) || state;
  }

  _getContainerHost(entity) {
    return entity.attributes && entity.attributes.host ? entity.attributes.host : this._t("unknown_host");
  }

  _getAllContainers() {
    if (!this._hass) return [];
    const failedEntityIds = this._getFailedEntityIds();
    const containers = Object.values(this._hass.states).filter((entity) =>
      entity.entity_id.startsWith("sensor.ssh_docker_") &&
      !failedEntityIds.has(entity.entity_id)
    );
    // Always sort alphabetically by display name.
    return containers.sort((a, b) => {
      const nameA = (a.attributes && a.attributes.name) || a.entity_id;
      const nameB = (b.attributes && b.attributes.name) || b.entity_id;
      return nameA.localeCompare(nameB);
    });
  }

  _getStateFilteredContainers() {
    const containers = this._getAllContainers();
    if (this._filter === "all") return containers;
    if (this._filter === "update_available") {
      return containers.filter((c) => c.attributes && c.attributes.update_available === true);
    }
    return containers.filter((c) => c.state === this._filter);
  }

  _getFilteredContainers() {
    const containers = this._getStateFilteredContainers();
    if (this._hostFilter === "all") return containers;
    return containers.filter((c) => this._getContainerHost(c) === this._hostFilter);
  }

  _setFilter(filter) {
    this._filter = filter;
    this._render();
  }

  _setHostFilter(host) {
    this._hostFilter = host;
    this._render();
  }

  _groupByHost(containers) {
    const groups = {};
    for (const entity of containers) {
      const host = this._getContainerHost(entity);
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
      case "starting":   return "#1abc9c";
      case "dead":       return "#8e44ad";
      case "created":    return "#16a085";
      case "removing":   return "#c0392b";
      case "stopping":   return "#e67e22";
      case "creating":   return "#2980b9";
      case "pulling":    return "#2471a3";
      case "refreshing": return "#7f8c8d";
      default:           return "#95a5a6";
    }
  }

  _renderContainerCard(entity) {
    const attrs = entity.attributes || {};
    const name = attrs.name || entity.entity_id;
    const state = entity.state || "unavailable";
    const image = attrs.image || "-";
    const haLocale =
      (this._hass && this._hass.locale && this._hass.locale.language) ||
      undefined;
    const formatDate = (dateStr) =>
      new Date(dateStr).toLocaleDateString(haLocale, {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      });
    const created = attrs.created ? formatDate(attrs.created) : "-";
    const updateBadge = attrs.update_available
      ? `<span class="update-badge">${this._t("update_available")}</span>`
      : "";
    const entityId = entity.entity_id;

    // Conditional button visibility per the requirements.
    // Create/Recreate: only if docker_create is available; label changes based on container state.
    const transitionalStates = ["creating", "initializing", "restarting", "starting", "stopping", "removing", "refreshing", "pulling"];
    const isTransitional = transitionalStates.includes(state);
    const showCreate   = !isTransitional && attrs.docker_create_available === true;
    const createLabel  = state !== "unavailable"
      ? (attrs.update_available && state === "running" ? this._t("btn_update") : this._t("btn_recreate"))
      : this._t("btn_create");
    // Start/Restart: show for running (Restart) or stopped states (Start).
    const stoppedStates = ["exited", "created", "dead", "paused"];
    const showRestart  = !isTransitional && state === "running";
    const showStart    = !isTransitional && stoppedStates.includes(state);
    const showStop     = !isTransitional && state === "running";
    const showRemove   = !isTransitional && state !== "unavailable" && state !== "unknown";
    const showRefresh  = state !== "initializing" && state !== "pulling";
    const showLogs     = state !== "unavailable" && state !== "unknown" && state !== "initializing" && state !== "pulling";

    const actionButtons = [
      showCreate  ? `<button class="action-btn create-btn"  data-action="create"  data-entity="${entityId}">${createLabel}</button>` : "",
      showRestart ? `<button class="action-btn restart-btn" data-action="restart" data-entity="${entityId}">${this._t("btn_restart")}</button>` : "",
      showStart   ? `<button class="action-btn restart-btn" data-action="restart" data-entity="${entityId}">${this._t("btn_start")}</button>`   : "",
      showStop    ? `<button class="action-btn stop-btn"    data-action="stop"    data-entity="${entityId}">${this._t("btn_stop")}</button>`    : "",
      showRemove  ? `<button class="action-btn remove-btn"  data-action="remove"  data-entity="${entityId}">${this._t("btn_remove")}</button>`  : "",
      showRefresh ? `<button class="action-btn refresh-btn" data-action="refresh" data-entity="${entityId}">${this._t("btn_refresh")}</button>` : "",
      showLogs    ? `<button class="action-btn logs-btn"    data-action="logs"    data-entity="${entityId}">${this._t("btn_logs")}</button>`    : "",
    ].filter(Boolean).join("");
    return `
      <div class="container-card">
        <div class="container-card-header" style="background:${this._stateColor(state)}">
          <span class="container-name">${name}</span>
          <span class="state-badge">${this._tState(state)}</span>
        </div>
        <div class="container-card-content">
          <table>
            <tr><td>Image</td><td class="image-cell">${image}</td></tr>
            <tr><td>${this._t("created_label")}</td><td>${created}</td></tr>
            ${attrs.update_available ? `<tr><td colspan="2">${updateBadge}</td></tr>` : ""}
          </table>
          ${actionButtons ? `<div class="action-buttons">${actionButtons}</div>` : ""}
        </div>
      </div>
    `;
  }

  _handleAction(action, entityId) {
    if (!this._hass) return;
    this._hass.callService("ssh_docker", action, { entity_id: entityId });
  }

  _render() {
    if (!this._hass) return;

    const allContainers = this._getAllContainers();

    const states = ["running", "exited", "paused", "restarting", "starting", "dead", "created", "removing", "stopping", "creating", "initializing", "pulling", "unavailable", "refreshing"];
    const counts = { all: allContainers.length };
    for (const s of states) {
      counts[s] = allContainers.filter((c) => c.state === s).length;
    }
    counts["update_available"] = allContainers.filter(
      (c) => c.attributes && c.attributes.update_available === true
    ).length;

    // If the active filter no longer has any containers, fall back to "all" before
    // computing stateFiltered/filteredContainers so the correct set is rendered.
    if (this._filter !== "all" && (counts[this._filter] === 0 || counts[this._filter] === undefined)) {
      this._filter = "all";
    }

    const stateFiltered = this._getStateFilteredContainers();
    const filteredContainers = this._getFilteredContainers();

    const filterKeys = ["all", ...states, "update_available"];
    const filterLabels = { update_available: this._t("updates_filter") };
    const filterButtons = filterKeys
      .filter((f) => f === "all" || counts[f] > 0)
      .map(
        (f) =>
          `<button class="filter-btn${this._filter === f ? " active" : ""}"
                   data-filter="${f}">
            ${filterLabels[f] || (f === "all" ? this._t("all_states") : this._tState(f))} (${counts[f]})
           </button>`
      )
      .join("");

    // Collect distinct hosts from all containers (for host filter visibility).
    const allHosts = [...new Set(
      allContainers.map((c) => this._getContainerHost(c))
    )].sort();

    // Host filter: only show when there are multiple distinct hosts.
    let hostFilterHtml = "";
    if (allHosts.length > 1) {
      // Count containers per host within the current state-filtered set.
      const hostCounts = { all: stateFiltered.length };
      for (const h of allHosts) {
        hostCounts[h] = stateFiltered.filter((c) => this._getContainerHost(c) === h).length;
      }
      const hostButtons = ["all", ...allHosts]
        .map(
          (h) =>
            `<button class="filter-btn host-filter-btn${this._hostFilter === h ? " active" : ""}"
                     data-host="${h}">
              ${h === "all" ? this._t("all_hosts") : h} (${hostCounts[h]})
             </button>`
        )
        .join("");
      hostFilterHtml = `<div class="filters host-filters">${hostButtons}</div>`;
    }

    const groups = this._groupByHost(filteredContainers);
    let hostsHtml = "";

    if (Object.keys(groups).length === 0) {
      hostsHtml = `<p class="no-containers">${this._t("no_containers")}</p>`;
    } else {
      for (const [host, hostContainers] of Object.entries(groups)) {
        const collapsed = this._collapsedHosts.has(host);
        const cards = hostContainers
          .map((c) => this._renderContainerCard(c))
          .join("");
        hostsHtml += `
          <div class="host-section">
            <h2 class="host-title" data-host="${host}">
              <span class="collapse-icon">${collapsed ? "▶" : "▼"}</span>
              🖥 ${host} (${hostContainers.length})
            </h2>
            <div class="container-grid${collapsed ? " hidden" : ""}">${cards}</div>
          </div>
        `;
      }
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        .toolbar {
          display: flex;
          align-items: center;
          background-color: var(--app-header-background-color, var(--primary-color));
          color: var(--app-header-text-color, white);
          height: var(--header-height, 56px);
          padding: 0 16px;
        }
        .toolbar-title {
          font-size: 1.25rem;
          font-weight: 500;
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .content {
          padding: 16px;
        }
        .filters {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 16px;
        }
        .host-filters {
          margin-top: -8px;
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
        .host-filter-btn {
          border-color: var(--secondary-text-color, #727272);
          color: var(--secondary-text-color, #727272);
        }
        .host-filter-btn.active {
          background: var(--secondary-text-color, #727272);
          color: white;
        }
        .host-filter-btn:hover:not(.active) {
          background: rgba(114, 114, 114, 0.1);
        }
        .host-section {
          margin-bottom: 24px;
        }
        .host-title {
          margin: 0 0 12px 0;
          font-size: 1.2rem;
          color: var(--secondary-text-color, #727272);
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          padding-bottom: 6px;
          cursor: pointer;
          user-select: none;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .host-title:hover {
          color: var(--primary-color, #03a9f4);
        }
        .collapse-icon {
          font-size: 0.7em;
          flex-shrink: 0;
        }
        .container-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
          gap: 16px;
        }
        .container-grid.hidden {
          display: none;
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
          font-size: 1.1rem;
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
        }
        .container-card-content {
          padding: 8px 16px 12px;
        }
        table { width: 100%; border-collapse: collapse; }
        td { padding: 4px 0; font-size: 1rem; color: var(--primary-text-color, #212121); }
        td:last-child {
          text-align: right;
          color: var(--secondary-text-color, #727272);
        }
        .image-cell { font-family: monospace; font-size: 0.8em; word-break: break-all; overflow-wrap: break-word; }
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
        .logs-btn    { background: #2c3e50; }
        .no-containers {
          color: var(--secondary-text-color, #727272);
          font-style: italic;
        }
        .failed-entries-section {
          margin-bottom: 24px;
        }
        .failed-section-title {
          margin: 0 0 12px 0;
          font-size: 1rem;
          color: #c0392b;
        }
        .setup-failed-hint {
          font-size: 0.85em;
          color: var(--secondary-text-color, #727272);
          margin: 4px 0 8px;
        }
        .setup-failed-host {
          font-size: 0.85em;
          color: var(--secondary-text-color, #727272);
          margin: 6px 0 0;
        }
        .open-settings-btn { background: #c0392b; }
      </style>
      <div class="toolbar">
        ${this._narrow ? "<ha-menu-button></ha-menu-button>" : ""}
        <div class="toolbar-title">SSH Docker</div>
      </div>
      <div class="content">
        ${this._renderFailedSection()}
        <div class="filters">${filterButtons}</div>
        ${hostFilterHtml}
        ${hostsHtml}
      </div>
    `;

    if (this._narrow) {
      const menuButton = this.shadowRoot.querySelector("ha-menu-button");
      if (menuButton) {
        menuButton.hass = this._hass;
        menuButton.narrow = this._narrow;
      }
    }

    // Use event delegation for host-title collapse toggles to avoid re-attaching per-element.
    this.shadowRoot.querySelector(".content").addEventListener("click", (e) => {
      const title = e.target.closest(".host-title");
      if (!title) return;
      const host = title.dataset.host;
      if (this._collapsedHosts.has(host)) {
        this._collapsedHosts.delete(host);
      } else {
        this._collapsedHosts.add(host);
      }
      this._render();
    });

    this.shadowRoot.querySelectorAll(".filter-btn:not(.host-filter-btn)").forEach((btn) => {
      btn.addEventListener("click", () => this._setFilter(btn.dataset.filter));
    });

    this.shadowRoot.querySelectorAll(".host-filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => this._setHostFilter(btn.dataset.host));
    });

    this.shadowRoot.querySelectorAll(".action-btn").forEach((btn) => {
      if (btn.dataset.action === "logs") {
        btn.addEventListener("click", () =>
          this._showLogs(btn.dataset.entity)
        );
      } else if (btn.classList.contains("open-settings-btn")) {
        btn.addEventListener("click", () => {
          history.pushState(null, "", btn.dataset.href);
          window.dispatchEvent(new CustomEvent("location-changed", { bubbles: true, composed: true }));
        });
      } else {
        btn.addEventListener("click", () =>
          this._handleAction(btn.dataset.action, btn.dataset.entity)
        );
      }
    });
  }

  async _showLogs(entityId) {
    if (!this._hass) return;
    const entity = this._hass.states[entityId];
    const containerName = (entity && entity.attributes && entity.attributes.name) || entityId;

    // Remove any existing overlay.
    const existing = document.getElementById("ssh-docker-logs-overlay");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "ssh-docker-logs-overlay";
    overlay.style.cssText = [
      "position:fixed", "inset:0", "background:rgba(0,0,0,0.7)",
      "z-index:9999", "display:flex", "align-items:center", "justify-content:center",
    ].join(";");

    const dialog = document.createElement("div");
    dialog.style.cssText = [
      "background:var(--card-background-color,#fff)", "border-radius:8px",
      "padding:24px", "max-width:90vw", "width:860px", "max-height:85vh",
      "display:flex", "flex-direction:column", "gap:12px", "box-sizing:border-box",
    ].join(";");

    const header = document.createElement("div");
    header.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;";
    const title = document.createElement("h2");
    title.style.cssText = "margin:0;font-size:1.1rem;color:var(--primary-text-color,#212121);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
    title.textContent = "📋 " + containerName;

    const refreshBtn = document.createElement("button");
    refreshBtn.style.cssText = [
      "padding:4px 12px", "border:none", "border-radius:12px", "cursor:pointer",
      "font-size:0.82em", "font-family:inherit", "font-weight:500",
      "background:#2c3e50", "color:white", "flex-shrink:0",
      "transition:background 0.3s",
    ].join(";");
    refreshBtn.textContent = this._t("logs_btn_refresh");
    refreshBtn.setAttribute("aria-label", this._t("logs_aria_refresh"));

    const autoLabel = document.createElement("label");
    autoLabel.style.cssText = "display:flex;align-items:center;gap:4px;font-size:0.78em;color:var(--primary-text-color,#212121);cursor:pointer;flex-shrink:0;white-space:nowrap;user-select:none;";
    const autoCheckbox = document.createElement("input");
    autoCheckbox.type = "checkbox";
    autoCheckbox.style.cssText = "cursor:pointer;margin:0;";
    autoCheckbox.setAttribute("aria-label", this._t("logs_aria_auto"));
    autoLabel.appendChild(autoCheckbox);
    autoLabel.appendChild(document.createTextNode(" " + this._t("logs_auto_label")));

    const timestamp = document.createElement("span");
    timestamp.style.cssText = "font-size:0.72em;color:var(--secondary-text-color,#727272);flex-shrink:0;white-space:nowrap;";

    const closeBtn = document.createElement("button");
    closeBtn.style.cssText = "background:none;border:none;cursor:pointer;font-size:1.4rem;line-height:1;color:var(--primary-text-color,#212121);flex-shrink:0;padding:0;";
    closeBtn.textContent = "✕";
    closeBtn.setAttribute("aria-label", this._t("logs_aria_close"));
    header.appendChild(title);
    header.appendChild(timestamp);
    header.appendChild(autoLabel);
    header.appendChild(refreshBtn);
    header.appendChild(closeBtn);

    const pre = document.createElement("pre");
    pre.style.cssText = [
      "overflow:auto", "flex:1", "min-height:200px", "max-height:65vh",
      "background:#1a1a2e", "color:#e0e0e0", "padding:12px",
      "border-radius:4px", "font-size:0.8em", "white-space:pre-wrap",
      "word-break:break-all", "margin:0",
    ].join(";");
    pre.textContent = this._t("logs_fetching");

    dialog.appendChild(header);
    dialog.appendChild(pre);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    let feedbackTimer = null;
    let autoRefreshInterval = null;
    let isFetching = false;

    const fetchLogs = async () => {
      if (isFetching) return;
      isFetching = true;
      refreshBtn.disabled = true;
      refreshBtn.textContent = this._t("logs_btn_loading");
      refreshBtn.style.background = "#7f8c8d";
      refreshBtn.setAttribute("aria-label", this._t("logs_aria_loading"));
      try {
        const result = await this._hass.connection.sendMessagePromise({
          type: "call_service",
          domain: "ssh_docker",
          service: "get_logs",
          service_data: { entity_id: entityId },
          return_response: true,
        });
        const logs = (result?.response?.logs) ?? "";
        pre.textContent = logs.trim() || this._t("logs_no_output");
        // Scroll to bottom so latest log entries are visible.
        pre.scrollTop = pre.scrollHeight;
        const now = new Date();
        timestamp.textContent = now.toLocaleTimeString(this._hass?.locale?.language || undefined);
        if (autoCheckbox.checked) {
          // Auto-refresh mode: skip the green flash, restore the button immediately.
          isFetching = false;
          refreshBtn.textContent = this._t("logs_btn_refresh");
          refreshBtn.style.background = "#2c3e50";
          refreshBtn.setAttribute("aria-label", this._t("logs_aria_refresh"));
          refreshBtn.disabled = false;
        } else {
          // Manual refresh: briefly flash green to confirm the refresh completed.
          refreshBtn.textContent = this._t("logs_btn_updated");
          refreshBtn.style.background = "#27ae60";
          feedbackTimer = setTimeout(() => {
            feedbackTimer = null;
            isFetching = false;
            refreshBtn.textContent = this._t("logs_btn_refresh");
            refreshBtn.style.background = "#2c3e50";
            refreshBtn.setAttribute("aria-label", this._t("logs_aria_refresh"));
            refreshBtn.disabled = false;
          }, 1500);
        }
      } catch (err) {
        pre.textContent = this._t("logs_fetch_error") + err;
        isFetching = false;
        refreshBtn.textContent = this._t("logs_btn_refresh");
        refreshBtn.style.background = "#2c3e50";
        refreshBtn.setAttribute("aria-label", this._t("logs_aria_refresh"));
        refreshBtn.disabled = false;
      }
    };

    const stopAutoRefresh = () => {
      if (autoRefreshInterval !== null) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
      }
    };

    autoCheckbox.addEventListener("change", () => {
      if (autoCheckbox.checked) {
        fetchLogs();
        autoRefreshInterval = setInterval(fetchLogs, 5000);
      } else {
        stopAutoRefresh();
      }
    });

    const closeOverlay = () => {
      stopAutoRefresh();
      if (feedbackTimer !== null) {
        clearTimeout(feedbackTimer);
        feedbackTimer = null;
      }
      overlay.remove();
    };

    closeBtn.addEventListener("click", closeOverlay);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeOverlay();
    });

    refreshBtn.addEventListener("click", fetchLogs);
    await fetchLogs();
  }
}

customElements.define("ssh-docker-panel", SshDockerPanel);

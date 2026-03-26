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

  _t(key) {
    return (this._hass && this._hass.localize(`component.ssh_docker.entity.ui.${key}.name`)) || key;
  }

  _tState(state) {
    return (this._hass && this._hass.localize(`component.ssh_docker.entity.sensor.state.state.${state}`)) || state;
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
      case "refreshing": return "#7f8c8d";
      default:           return "#95a5a6";
    }
  }

  _handleAction(action, entityId) {
    if (!this._hass) return;
    this._hass.callService("ssh_docker", action, { entity_id: entityId });
  }

  _render() {
    if (!this._hass || !this.config) return;

    const entityId = this.config.entity;
    const entity = this._hass.states[entityId];
    const attrs = (entity && entity.attributes) || {};
    const state = (entity && entity.state) || "unavailable";
    const name = attrs.name || entityId;
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
    const host = attrs.host || "-";
    const updateBadge = attrs.update_available
      ? `<span class="update-badge">${this._t("update_available")}</span>`
      : "";

    // Conditional button visibility — same logic as the panel.
    const transitionalStates = ["creating", "restarting", "stopping", "removing", "refreshing"];
    const isTransitional = transitionalStates.includes(state);
    const showCreate   = !isTransitional && attrs.docker_create_available === true;
    const createLabel  = state !== "unavailable"
      ? (attrs.update_available && state === "running" ? this._t("btn_update") : this._t("btn_recreate"))
      : this._t("btn_create");
    const stoppedStates = ["exited", "created", "dead", "paused"];
    const showRestart  = !isTransitional && state === "running";
    const showStart    = !isTransitional && stoppedStates.includes(state);
    const showStop     = !isTransitional && state === "running";
    const showRemove   = !isTransitional && state !== "unavailable" && state !== "unknown";
    const showRefresh  = state !== "refreshing";
    const showLogs     = state !== "unavailable" && state !== "unknown" && state !== "initializing";

    const actionButtons = [
      showCreate  ? `<button class="action-btn create-btn"  data-action="create"  data-entity="${entityId}">${createLabel}</button>` : "",
      showRestart ? `<button class="action-btn restart-btn" data-action="restart" data-entity="${entityId}">${this._t("btn_restart")}</button>` : "",
      showStart   ? `<button class="action-btn restart-btn" data-action="restart" data-entity="${entityId}">${this._t("btn_start")}</button>`   : "",
      showStop    ? `<button class="action-btn stop-btn"    data-action="stop"    data-entity="${entityId}">${this._t("btn_stop")}</button>`    : "",
      showRemove  ? `<button class="action-btn remove-btn"  data-action="remove"  data-entity="${entityId}">${this._t("btn_remove")}</button>`  : "",
      showRefresh ? `<button class="action-btn refresh-btn" data-action="refresh" data-entity="${entityId}">${this._t("btn_refresh")}</button>` : "",
      showLogs    ? `<button class="action-btn logs-btn"    data-action="logs"    data-entity="${entityId}">${this._t("btn_logs")}</button>`    : "",
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
          font-size: 1.1rem;
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
          flex-shrink: 0;
        }
        .card-content {
          padding: 10px 16px 14px;
        }
        table { width: 100%; border-collapse: collapse; }
        td { padding: 4px 0; font-size: 1em; color: var(--primary-text-color); }
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
        .logs-btn    { background: #2c3e50; }
      </style>
      <ha-card>
        <div class="card-header">
          <span>${name}</span>
          <span class="badge">${this._tState(state)}</span>
        </div>
        <div class="card-content">
          <table>
            <tr><td>${this._t("host_label")}</td><td>${host}</td></tr>
            <tr><td>Image</td><td class="image">${image}</td></tr>
            <tr><td>${this._t("created_label")}</td><td>${created}</td></tr>
            ${attrs.update_available ? `<tr><td colspan="2">${updateBadge}</td></tr>` : ""}
          </table>
          <div class="action-buttons">${actionButtons}</div>
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".action-btn").forEach((btn) => {
      if (btn.dataset.action === "logs") {
        btn.addEventListener("click", () =>
          this._showLogs(btn.dataset.entity)
        );
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

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return { rows: 3, columns: 6, min_rows: 2 };
  }
}

customElements.define("ssh-docker-card", SshDockerCard);

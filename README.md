# 🐳 SSH Docker

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/gensyn/ssh_docker.svg)](https://github.com/gensyn/ssh_docker/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant custom component that monitors and controls Docker containers on remote hosts over SSH. All communication with the remote host is performed through the [`ssh_command`](https://github.com/gensyn/ssh_command) integration, which must be installed as a dependency.

---

## ✨ Features

- 🐳 **Docker Container Monitoring** — Track the state, image, and creation date of containers on remote hosts
- 🔄 **Auto-Update Detection** — Automatically detects when a newer image is available upstream
- 🤖 **Auto-Update** — Optionally recreate containers when a newer image is detected
- 🔔 **HA Update Entities** — Containers with available image updates appear natively in Home Assistant's **Settings → Updates** panel and can be installed from there with one click
- 🔍 **Automatic Discovery** — Discovers all containers on a host and offers to add them to Home Assistant
- 🎛️ **Full Container Control** — Create, start, restart, stop, remove, and execute arbitrary commands in containers from within Home Assistant
- 📊 **Sidebar Panel** — Auto-registered dashboard listing all containers grouped by host with filtering
- 🎴 **Lovelace Card** — Individual container card for any Lovelace dashboard
- 📡 **SSH Transport** — All host communication is delegated to `ssh_command.execute` — no direct SSH dependencies in this integration

---

## 🖥️ Compatibility

### Home Assistant

SSH Docker works with any Home Assistant installation that supports custom components (Core, Supervised, OS, Container). No specific minimum version is enforced beyond what the underlying `ssh_command` dependency requires.

### Remote Host (Docker Host)

The remote host where your containers run **must be a Linux system**. SSH Docker issues standard Linux shell commands over SSH (e.g. `docker inspect`, `docker ps`, `docker restart`, `command -v …`) and relies on a POSIX shell environment. Non-Linux SSH targets (e.g. native Windows Server, macOS without a Linux VM) are not supported.

Expected to work with:

- Any Linux distribution with a working SSH server (OpenSSH or compatible)
- Docker CE / EE
- [Podman](https://podman.io/) (set **Docker command** to `podman` or `sudo podman`) - **untested**
- Any other Docker-compatible CLI that accepts the same `ps`, `inspect`, `pull`, `restart`, `stop`, and `rm` subcommands

### SSH

An SSH server (e.g. OpenSSH `sshd`) must be running and reachable on the remote host. Authentication via password or SSH private key is supported.

---

## 🚀 Installation

### Prerequisites

This integration depends on the [SSH Command](https://github.com/gensyn/ssh_command) integration. It should be automatically installed when installing SSH Docker through HACS or you can install it first manually:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gensyn&repository=ssh_command&category=integration)

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gensyn&repository=ssh_docker&category=integration)

1. Click the badge above or search for **SSH Docker** in HACS
2. Click **Download**
3. Restart Home Assistant
4. Add the integration via `Settings > Devices & Services > Add Integration`

### Manual Installation

1. Ensure **SSH Command** is already installed
2. Download or clone this repository
3. Copy the `ssh_docker` folder to your Home Assistant `config/custom_components` directory
4. Restart Home Assistant
5. Add the integration via `Settings > Devices & Services > Add Integration`

---

## 📖 Configuration

### Adding a Container

Navigate to `Settings > Devices & Services > Add Integration` and search for **SSH Docker**.

Fill in the following fields:

| Field | Required | Description |
|-------|----------|-------------|
| **Name** | ✅ | Friendly display name for this entry (must be unique across all entries) |
| **Service** | ✅ | Name of the Docker container on the remote host |
| **Host** | ✅ | Hostname or IP address of the remote server |
| **Username** | ✅ | SSH username |
| **Password** | ⚠️ | SSH password (use instead of `key_file`) |
| **Key file** | ⚠️ | Path to an SSH private key file on the HA host (use instead of `password`) |
| **Check known hosts** | — | Verify host key against known hosts (default: `true`) |
| **Known hosts** | — | Path or string of the known hosts (only valid when `check_known_hosts` is `true`) |
| **Docker command** | — | The Docker executable on the remote host, e.g. `docker`, `sudo docker`, `podman` (default: `docker`) |
| **Check for updates** | — | When enabled, checks for newer upstream images during each sensor update (default: `false`) |
| **Auto update** | — | When enabled and an update is detected, automatically recreates the container (requires `docker_create`; default: `false`) |

> **Note:** Either `password` or `key_file` must be provided.

When a new entry is added the integration validates the SSH connection and verifies that the named container exists on the host before creating the entry.

### ⚙️ Options

After an entry is created, click the cog icon ⚙️ to adjust its settings. All SSH and Docker fields are editable in options.

> **Note:** `Name` and `Service` cannot be changed after the entry is created.

---

## 📡 Sensor

Each configured container creates a **sensor** entity named `sensor.ssh_docker_<name>`.

### State

The sensor state reflects the current Docker container state:

| State | Meaning |
|-------|---------|
| `running` | Container is running |
| `exited` | Container has stopped |
| `created` | Container exists but has never been started |
| `paused` | Container is paused |
| `dead` | Container is dead |
| `unavailable` | Container does not exist or SSH connection failed |
| `creating` | `create` service is executing |
| `restarting` | `restart` service is executing |
| `stopping` | `stop` service is executing |
| `removing` | `remove` service is executing |

The sensor is updated every **24 hours** by default, or on demand via the **Refresh** action.

### Attributes

| Attribute | Description |
|-----------|-------------|
| `name` | Friendly display name of the container (language-independent; used by the panel and Lovelace card) |
| `host` | Remote host the container runs on |
| `image` | Docker image name |
| `created` | Container creation timestamp |
| `update_available` | `true` when a newer upstream image is available (only set when `check_for_updates` is enabled) |
| `docker_create_available` | `true` when the `docker_create` executable is present on the remote host |

---

## 🔔 Update Entity

When **Check for updates** is enabled for a container entry, SSH Docker also creates an **update** entity named `update.ssh_docker_<name>` for each configured container. This entity integrates with Home Assistant's native update mechanism so that pending image updates are surfaced in **Settings → Updates** alongside other HA and add-on updates.

### How it works

- After each sensor poll the update entity is automatically refreshed. When a newer upstream image is detected (`update_available: true`) the entity state becomes **on** (update available).
- When no update is pending, or the container is unreachable, the entity state is **off**.
- The update entity is linked to the same **device** as the container sensor, so both appear together in the device detail page.

### Installing an update from the UI

Navigate to **Settings → Updates** in Home Assistant. Containers with a pending image update are listed there. Click the container's update card and then **Install** to trigger a container recreation using the `docker_create` executable on the remote host — exactly the same operation as clicking **⬆ Update** in the sidebar panel.

> **Requires** the `docker_create` executable to be present on the remote host. See [Custom Executables](#%EF%B8%8F-custom-executables) for details.

While the installation is running the entity reports `in_progress: true` and the update card shows a progress indicator. Once completed the sensor is refreshed automatically to reflect the new container state.

---

## 🔧 Services

SSH Docker provides the following services in the `ssh_docker` domain. All services target a container sensor via `entity_id`.

### `ssh_docker.create`

Creates (or recreates) the Docker container using the `docker_create` executable on the remote host.

> **Requires** the `docker_create` executable to be present on the remote host's `PATH` or at `/usr/bin/docker_create`. The executable receives the container name as its sole argument.

The sensor state transitions to `creating` while the operation runs. Non-zero exit codes from `docker_create` are treated as warnings (not errors) since cleanup steps in creation scripts often exit non-zero harmlessly. The timeout is **10 minutes**.

```yaml
action: ssh_docker.create
target:
  entity_id: sensor.ssh_docker_grocy
```

### `ssh_docker.restart`

Restarts the Docker container (also works to start a stopped/exited container). The sensor state transitions to `restarting` while the operation runs.

```yaml
action: ssh_docker.restart
target:
  entity_id: sensor.ssh_docker_grocy
```

### `ssh_docker.stop`

Stops the Docker container. The sensor state transitions to `stopping` while the operation runs.

```yaml
action: ssh_docker.stop
target:
  entity_id: sensor.ssh_docker_grocy
```

### `ssh_docker.remove`

Stops and removes the Docker container. The sensor state transitions to `removing` while the operation runs.

```yaml
action: ssh_docker.remove
target:
  entity_id: sensor.ssh_docker_grocy
```

### `ssh_docker.refresh`

Triggers an immediate sensor update for the container (fetches fresh state from the remote host). Useful for automation-driven polling or after an out-of-band change.

```yaml
action: ssh_docker.refresh
target:
  entity_id: sensor.ssh_docker_grocy
```

### `ssh_docker.get_logs`

Returns the last 200 lines of the container's logs (stdout + stderr combined). The response is available via the `logs` key.

```yaml
action: ssh_docker.get_logs
target:
  entity_id: sensor.ssh_docker_grocy
response_variable: result
# result.logs contains the log output string
```

### `ssh_docker.execute_command`

Executes an arbitrary command inside the running Docker container via `docker exec` and returns the combined stdout + stderr output along with the exit status. The command is passed to `sh -c` inside the container.

```yaml
action: ssh_docker.execute_command
data:
  entity_id: sensor.ssh_docker_grocy
  command: "cat /etc/os-release"
response_variable: result
# result.output     — combined stdout + stderr of the command
# result.exit_status — integer exit code returned by the command
```

This service is useful for one-off diagnostic commands, health checks, or configuration queries without requiring a separate SSH session.

---

## 🔍 Automatic Discovery

When a new entry is successfully added, SSH Docker automatically scans the host for additional Docker containers and offers to add unconfigured ones as new entries. The discovery form is pre-filled with all SSH and Docker settings from the original entry — including the `check_for_updates` and `auto_update` values — so the user only needs to confirm the container name.

Discovered container names are automatically capitalized in the **Name** field (e.g., `grocy` → `Grocy`) while the **Service** field retains the original lowercase name.

**Discovery logic:**
1. If `docker_services` is present on the remote host's `PATH` or at `/usr/bin/docker_services`, it is called and its output is parsed as a list of container names (JSON array, or names separated by spaces, commas, or newlines).
2. Otherwise, the integration falls back to listing all containers via `docker ps -a`, whose output is also parsed flexibly (any combination of spaces, commas, or newlines).

---

## 📊 Sidebar Panel

A **SSH Docker** entry is automatically added to the Home Assistant sidebar when the integration is installed — no manual dashboard setup required.

The panel shows all containers grouped by host with live filtering:

### State filter

| Filter | Shows |
|--------|-------|
| **All states** | Every container |
| **running** | Running containers |
| **exited** | Stopped containers |
| **unavailable** | Unreachable containers |
| **⬆ updates (N)** | Containers with a newer image available (shown only when applicable) |

### Host filter

When containers span more than one host, a second filter row appears beneath the state filter. It shows **All Hosts** plus a button for each individual host. Host and state filters can be combined — for example, selecting **running** and then **myserver** shows only running containers on that host.

Each container card displays the current state (color-coded), image, creation date, and an **⬆ Update available** badge when applicable. Action buttons are shown conditionally:

| Button | Condition |
|--------|-----------|
| **✚ Create** | `docker_create_available` is `true` and container is `unavailable` |
| **✚ Recreate** | `docker_create_available` is `true`, container exists, and no update is pending |
| **⬆ Update** | `docker_create_available` is `true`, container is `running`, and `update_available` is `true` |
| **▶ Start** | Container is `exited`, `created`, `dead`, or `paused` |
| **↺ Restart** | Container is `running` |
| **■ Stop** | Container is `running` |
| **🗑 Remove** | Container is not `unavailable` |
| **↻ Refresh** | Always shown; triggers an immediate sensor update |

The panel is mobile-friendly: on narrow screens a hamburger menu button (`☰`) appears in the toolbar to open the Home Assistant sidebar.

---

## 🎴 Lovelace Card

An individual container card is also available for any Lovelace dashboard:

```yaml
type: custom:ssh-docker-card
entity: sensor.ssh_docker_grocy
```

The card displays the container's state, image, creation date, and an **⬆ Update available** badge when applicable. It includes the same action buttons as the sidebar panel with identical visibility conditions:

| Button | Condition |
|--------|-----------|
| **✚ Create** | `docker_create_available` is `true` and container is `unavailable` |
| **✚ Recreate** | `docker_create_available` is `true`, container exists, and no update is pending |
| **⬆ Update** | `docker_create_available` is `true`, container is `running`, and `update_available` is `true` |
| **▶ Start** | Container is `exited`, `created`, `dead`, or `paused` |
| **↺ Restart** | Container is `running` |
| **■ Stop** | Container is `running` |
| **🗑 Remove** | Container is not `unavailable` |
| **↻ Refresh** | Always shown; triggers an immediate sensor update |

---

## 🛠️ Custom Executables

SSH Docker integrates with two optional executables on the remote host:

### `docker_create`

Required for the `create` service and auto-update functionality. Place this script on the remote host's `PATH` or at `/usr/bin/docker_create`. It receives the container name as the first argument and is responsible for creating (or recreating) the container in whatever way is appropriate for your setup.

**Example `docker_create` script:**
```bash
#!/bin/bash
set -e
SERVICE=$1
docker compose -f /opt/docker/${SERVICE}/docker-compose.yml up -d
```

### `docker_services`

Optional. If present on the remote host's `PATH` or at `/usr/bin/docker_services`, it is used during discovery to list available containers. Its output is parsed flexibly: a JSON array of strings is preferred, but whitespace-, comma-, or newline-separated names are also accepted.

**Example `docker_services` script:**
```bash
#!/bin/bash
docker ps -a --format '{{.Names}}' | python3 -c "import sys, json; print(json.dumps(sys.stdin.read().split()))"
```

---

## ⚡ Performance & Reliability

### SSH Concurrency Limiting

SSH Docker uses **per-host semaphores** to cap concurrent SSH connections to a maximum of **3 per host**. This prevents overloading the remote SSH server when many containers are configured on the same host, avoiding `Connection lost` errors that would otherwise occur when many sensors update simultaneously.

### Startup Deferral

When Home Assistant starts, each sensor defers its first SSH update until after the `homeassistant_started` event.

### `docker_create` Availability Cache

The check for whether `docker_create` is present on the remote host is performed **once per host per poll cycle** (cached for 24 hours). All containers on the same host reuse the cached result, so only one SSH round-trip is made per host regardless of how many containers are configured.

---

## 🌍 Translations

SSH Docker ships with translations for the following languages:

| Language | Code |
|----------|------|
| English | `en` |
| German | `de` |

Community contributions for additional languages are welcome!

---

## ⚠️ Known Issues

- If you are using HassOS and enable `check_known_hosts` without explicitly providing `known_hosts`, this may fail because the default known hosts file may not be accessible from within Home Assistant. Either disable host checking (not recommended) or provide `known_hosts` explicitly.
- `docker_create` scripts that run cleanup commands (e.g. `docker rm`) before creating a container may exit non-zero even on success. SSH Docker logs these as warnings rather than errors; the actual container state is always verified after the operation.

---

## 🚧 Future Development

Have ideas or feature requests? I'm open to suggestions!

- 🌍 **Additional Translations** — Community contributions welcome for your language
- 🎯 **Your Ideas** — Open an issue to suggest new features!

---

## 🤝 Contributing

Contributions are welcome! Feel free to:
- 🐛 Report bugs via [Issues](https://github.com/gensyn/ssh_docker/issues)
- 💡 Suggest features
- 🌐 Contribute translations
- 📝 Improve documentation

---

## 📄 License

This project is licensed under the terms specified in the [MIT License](https://mit-license.org/).

---

## ⭐ Support

If you find SSH Docker useful, please consider giving it a star on GitHub! It helps others discover the project.

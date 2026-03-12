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
- 🔍 **Automatic Discovery** — Discovers all containers on a host and offers to add them to Home Assistant
- 🎛️ **Full Container Control** — Create, start, restart, stop, and remove containers from within Home Assistant
- 📊 **Sidebar Panel** — Auto-registered dashboard listing all containers grouped by host with filtering
- 🎴 **Lovelace Card** — Individual container card for any Lovelace dashboard
- 📡 **SSH Transport** — All host communication is delegated to `ssh_command.execute` — no direct SSH dependencies in this integration

---

## 🚀 Installation

### Prerequisites

This integration depends on the [SSH Command](https://github.com/gensyn/ssh_command) integration. Install it first:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gensyn&repository=ssh_command&category=integration)

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gensyn&repository=ssh_docker&category=integration)

1. Ensure **SSH Command** is already installed (see above)
2. Click the badge above or search for **SSH Docker** in HACS
3. Click **Download**
4. Restart Home Assistant
5. Add the integration via `Settings > Devices & Services > Add Integration`

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

> **Note:** Either `password` or `key_file` must be provided.

When a new entry is added the integration validates the SSH connection and verifies that the named container exists on the host before creating the entry.

### ⚙️ Options

After an entry is created, click the cog icon ⚙️ to adjust its settings. All SSH and Docker fields are editable in options. Additionally:

| Option | Description |
|--------|-------------|
| **Auto update** | When enabled, automatically recreates the container when a newer image is detected (requires `docker_create` on the remote host; default: `false`) |

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
| `host` | Remote host the container runs on |
| `image` | Docker image name |
| `created` | Container creation timestamp |
| `update_available` | `true` when a newer upstream image is available |
| `docker_create_available` | `true` when the `docker_create` executable is present on the remote host |

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
  entity_id: sensor.ssh_docker_beets
```

### `ssh_docker.restart`

Restarts the Docker container (also works to start a stopped/exited container). The sensor state transitions to `restarting` while the operation runs.

```yaml
action: ssh_docker.restart
target:
  entity_id: sensor.ssh_docker_beets
```

### `ssh_docker.stop`

Stops the Docker container. The sensor state transitions to `stopping` while the operation runs.

```yaml
action: ssh_docker.stop
target:
  entity_id: sensor.ssh_docker_beets
```

### `ssh_docker.remove`

Stops and removes the Docker container. The sensor state transitions to `removing` while the operation runs.

```yaml
action: ssh_docker.remove
target:
  entity_id: sensor.ssh_docker_beets
```

---

## 🔍 Automatic Discovery

When a new entry is successfully added, SSH Docker automatically scans the host for additional Docker containers and offers to add unconfigured ones as new entries. The discovery form is pre-filled with all SSH and Docker settings from the original entry — only the container name needs to be confirmed.

**Discovery logic:**
1. If `docker_services` is present on the remote host's `PATH` or at `/usr/bin/docker_services`, it is called and expected to return a JSON list of container name strings.
2. Otherwise, the integration falls back to listing all containers via `docker ps -a`.

---

## 📊 Sidebar Panel

A **SSH Docker** entry is automatically added to the Home Assistant sidebar when the integration is installed — no manual dashboard setup required.

The panel shows all containers grouped by host with live filtering:

| Filter | Shows |
|--------|-------|
| **All** | Every container |
| **running** | Running containers |
| **exited** | Stopped containers |
| **unavailable** | Unreachable containers |
| **⬆ updates (N)** | Containers with a newer image available (shown only when applicable) |

Each container card displays the current state (color-coded), image, creation date, and an **⬆ Update available** badge when applicable. Action buttons are shown conditionally:

| Button | Condition |
|--------|-----------|
| **✚ Create** / **✚ Recreate** | `docker_create_available` is `true`; label is "Create" when `unavailable`, "Recreate" otherwise |
| **↺ Restart** | Container is `running` |
| **▶ Start** | Container is `exited`, `created`, `dead`, or `paused` |
| **■ Stop** | Container is `running` |
| **🗑 Remove** | Container is not `unavailable` |
| **↻ Refresh** | Always shown; triggers an immediate sensor update |

---

## 🎴 Lovelace Card

An individual container card is also available for any Lovelace dashboard:

```yaml
type: custom:ssh-docker-card
entity: sensor.ssh_docker_beets
```

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

Optional. If present on the remote host's `PATH` or at `/usr/bin/docker_services`, it is used during discovery to list available containers. It must return a JSON array of container name strings to stdout.

**Example `docker_services` script:**
```bash
#!/bin/bash
docker ps -a --format '{{.Names}}' | python3 -c "import sys, json; print(json.dumps(sys.stdin.read().split()))"
```

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

# SSH Docker Playwright E2E Tests

End-to-end tests for the **SSH Docker** Home Assistant custom component using
[Playwright](https://playwright.dev/python/).

## Running with Docker (recommended)

The repository ships a `docker-compose.yaml` that starts Home Assistant, a mock
Docker host, and a self-contained Playwright test-runner — no local Python
environment or browser installation required.

```bash
# From the repository root:

# First run: build the images (only needed once, or after code changes)
docker compose build

# Run the full E2E suite
docker compose run --rm playwright-tests

# Stop background services and remove volumes when done
docker compose down -v
```

On the **first run** the test-runner container automatically creates the HA
admin user via the onboarding API, so no manual UI interaction is needed.

Test results (JUnit XML) are written to `playwright-results/` in the repository
root and can be used by CI or inspected locally.

## Running the full CI suite locally

`run_workflows_locally.sh` includes the Playwright E2E tests.  It calls
`docker compose run` directly instead of going through `act`:

```bash
./run_workflows_locally.sh
```

## Debugging in PyCharm

You can run and debug the tests directly from PyCharm by pointing them at the
infrastructure containers running on `localhost`.

**1. Expose the container ports**

Copy the provided example override file and bring up only the infrastructure:

```bash
cp docker-compose.override.yaml.example docker-compose.override.yaml
docker compose up -d homeassistant docker-host
```

The override exposes:
- Home Assistant at `http://localhost:8123`
- The mock Docker host SSH at `localhost:2222`

**2. Set up Home Assistant (first run only)**

On the first start HA needs to be onboarded.  Open `http://localhost:8123` in
your browser and complete the onboarding wizard (create admin user / password
`admin`/`admin` to match the test defaults), then navigate to
**Settings → Devices & Services → Add Integration** and add **SSH Command**
(no configuration needed — just click through).

Alternatively, run the automated setup script once:

```bash
HA_URL=http://localhost:8123 bash tests/playwright/entrypoint.sh --collect-only 2>/dev/null || true
```

**3. Configure the PyCharm run/debug configuration**

1. Open **Run → Edit Configurations** and add a new **pytest** configuration.
2. Set **Script path** to `tests/playwright/` (the directory).
3. Add the following **environment variables**:

| Variable | Value |
|---|---|
| `HOMEASSISTANT_URL` | `http://localhost:8123` |
| `DOCKER_HOST_NAME` | `localhost` |
| `SSH_USER` | `foo` |
| `SSH_PASSWORD` | `pass` |
| `HA_USERNAME` | `admin` |
| `HA_PASSWORD` | `admin` |

4. Set **Working directory** to `tests/playwright/`.
5. Ensure the Python interpreter has the test dependencies installed:
   ```bash
   pip install -r tests/playwright/requirements.txt
   playwright install chromium
   ```

You can now set breakpoints anywhere in the test files and launch the
configuration with the **Debug** button.

> **Note:** `DOCKER_HOST_NAME=localhost` tells the tests to connect to SSH on
> `localhost`; the port mapping in `docker-compose.override.yaml` routes that
> to the container on port 2222.  If HA's `ssh_command` component still uses
> the internal Docker hostname `docker_host`, you may need to add a hosts entry
> or adjust the test's `conftest.py` `DOCKER_HOST_NAME` default.

## Running without Docker (advanced)

```bash
# Install dependencies
pip install -r tests/playwright/requirements.txt
playwright install chromium

# Point at your services
export HOMEASSISTANT_URL=http://localhost:8123
export DOCKER_HOST_NAME=my-docker-host
export SSH_USER=foo
export SSH_PASSWORD=pass
export HA_USERNAME=admin
export HA_PASSWORD=admin

pytest tests/playwright/ -v
```

## GitHub Actions

The `.github/workflows/playwright-tests.yml` workflow runs the full suite on
manual dispatch.  It builds the images, calls `docker compose run playwright-tests`,
and uploads `playwright-results/junit.xml` as a workflow artifact.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HOMEASSISTANT_URL` | `http://homeassistant:8123` | Home Assistant base URL |
| `DOCKER_HOST_NAME` | `docker_host` | Hostname of the Docker SSH host |
| `SSH_USER` | `foo` | SSH username for the Docker host |
| `SSH_PASSWORD` | `pass` | SSH password for the Docker host |
| `HA_USERNAME` | `admin` | Home Assistant admin username |
| `HA_PASSWORD` | `admin` | Home Assistant admin password |

## Docker image layout

| File | Purpose |
|---|---|
| `Dockerfile` | Playwright test-runner (Python 3.12 + Chromium) |
| `Dockerfile.dockerhost` | Docker host (Ubuntu 24.04 + openssh + mock Docker CLI) |
| `mock-docker.sh` | Mock Docker CLI that simulates container lifecycle using state files |
| `docker-host-entrypoint.sh` | Container startup: create mock containers, start sshd |
| `ha-init-wrapper.sh` | HA container startup: pre-populate /etc/hosts, then exec /init |
| `entrypoint.sh` | Test runner startup: wait for HA → onboard → setup ssh_command → run pytest |
| `ssh_command/` | Functional copy of the ssh_command HA component (required by ssh_docker) |

## Test Modules

| File | What it tests |
|---|---|
| `test_integration_setup.py` | Config flow: add, duplicate rejection, lifecycle |
| `test_sensor.py` | Sensor entity creation, state, attributes, refresh |
| `test_services.py` | restart, stop, get_logs, refresh, invalid entity handling |
| `test_frontend.py` | HA frontend pages, SSH Docker panel, integrations list |
| `test_configuration.py` | Auth options, multiple entries, invalid credentials |
| `test_security.py` | Unauthenticated API rejection, invalid credentials, unreachable hosts |

## Fixtures (`conftest.py`)

| Fixture | Scope | Description |
|---|---|---|
| `playwright_instance` | session | Playwright instance |
| `browser` | session | Headless Chromium browser |
| `ha_base_url` | session | Configured HA URL |
| `ha_token` | session | Long-lived HA access token |
| `context` | function | Authenticated browser context |
| `page` | function | Fresh page within the authenticated context |
| `docker_host` | session | Connection parameters for the Docker SSH host |
| `ha_api` | function | `requests.Session` for the HA REST API |
| `ensure_integration` | function | Adds ssh_docker entry; fully restores state after test |

## Notes

- Tests are **idempotent** – each test cleans up after itself.
- Tests do **not** depend on each other.
- The mock Docker CLI (`mock-docker.sh`) simulates container state using plain files —
  no Docker daemon or privileged mode required.
- Browser-based tests use a headless Chromium instance.
- API-based tests call Home Assistant's REST API directly for speed.

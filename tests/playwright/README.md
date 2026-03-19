# SSH Docker Playwright End-to-End Tests

This directory contains comprehensive Playwright end-to-end tests for the SSH Docker Home Assistant custom component.

## Test Environment

Tests require a running environment with:
- **Home Assistant** instance (default: `http://homeassistant:8123`)
- **SSH Docker test host** with Docker daemon (default: `ssh_docker_test:22`)
  - Two pre-running containers: `ssh_test_1` and `ssh_test_2`
  - SSH credentials: `root` / `testpassword`

The recommended way to spin up this environment is with the `docker-compose.yaml` at the repository root.

## Test Files

| File | Description |
|------|-------------|
| `conftest.py` | Shared fixtures: HA session, browser context, integration setup/teardown |
| `test_integration_setup.py` | Config flow via UI and REST API, duplicate detection |
| `test_container_discovery.py` | Sensor creation, container state detection |
| `test_container_management.py` | Stop, restart, remove, create service calls |
| `test_sensors.py` | Sensor state validity, attribute assertions, state transitions |
| `test_services.py` | All five `ssh_docker.*` services registered and callable |
| `test_frontend.py` | Integrations page, Developer Tools, panel navigation |
| `test_updates.py` | Update entity creation, version attributes, auto-update option |
| `test_configuration.py` | Options flow, multiple entries, entry deletion |

## Installation

```bash
cd tests/playwright
pip install -r requirements.txt
playwright install chromium
```

## Configuration

Set the following environment variables (or rely on defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOMEASSISTANT_URL` | `http://homeassistant:8123` | HA base URL |
| `HA_USERNAME` | `admin` | HA owner username |
| `HA_PASSWORD` | `adminpassword` | HA owner password |
| `SSH_HOST` | `ssh_docker_test` | Docker host SSH address |
| `DOCKER_SSH_PORT` | `22` | SSH port on Docker host |
| `DOCKER_SSH_USER` | `root` | SSH username |
| `DOCKER_SSH_PASSWORD` | `testpassword` | SSH password |

## Running Tests

### Run all tests

```bash
cd tests/playwright
pytest -v
```

### Run a specific test file

```bash
pytest test_integration_setup.py -v
```

### Run a specific test

```bash
pytest test_services.py::TestServiceRegistration::test_all_services_registered -v
```

### Run with environment overrides

```bash
HOMEASSISTANT_URL=http://localhost:8123 \
HA_PASSWORD=mypassword \
SSH_HOST=localhost \
pytest -v
```

### Run inside Docker (via docker-compose)

```bash
# Start the test environment
docker-compose up -d homeassistant ssh_docker_test

# Wait for HA to initialise (check with: curl http://localhost:8123/api/)

# Run the tests
docker-compose run --rm playwright pytest tests/playwright -v
```

## Notes

- Tests are **idempotent**: each test cleans up integration entries it creates
- Tests use `pytest.skip()` when required infrastructure (running containers, SSH) is unavailable
- Playwright browser tests require a running HA frontend; some tests fall back gracefully
- Service tests verify HTTP 200/204 responses from HA, not Docker-level outcomes (which depend on SSH connectivity)
- Update entity tests depend on `check_for_updates=True` being set during integration setup

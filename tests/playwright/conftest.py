"""Pytest configuration and fixtures for SSH Docker Playwright E2E tests."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Generator

import pytest
import requests
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# ---------------------------------------------------------------------------
# Environment-variable driven configuration
# ---------------------------------------------------------------------------

HA_URL: str = os.environ.get("HOMEASSISTANT_URL", "http://homeassistant:8123")
DOCKER_HOST_NAME: str = os.environ.get("DOCKER_HOST_NAME", "docker_host")
SSH_USER: str = os.environ.get("SSH_USER", "foo")
SSH_PASSWORD: str = os.environ.get("SSH_PASSWORD", "pass")

HA_USERNAME: str = os.environ.get("HA_USERNAME", "admin")
HA_PASSWORD: str = os.environ.get("HA_PASSWORD", "admin")

# Test container names pre-created on the docker_host
TEST_CONTAINER_1 = "test-app"
TEST_CONTAINER_2 = "test-app-2"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HA_TOKEN: str | None = None


def get_ha_token() -> str:
    """Obtain a Home Assistant access token via the login flow.

    On the first call the token is fetched and cached for the remainder of
    the test session.  Retries up to 5 times with a short delay to handle
    the window immediately after HA onboarding completes.
    """
    global _HA_TOKEN  # noqa: PLW0603
    if _HA_TOKEN:
        return _HA_TOKEN

    last_exc: Exception | None = None
    for attempt in range(5):
        if attempt:
            time.sleep(5)
        try:
            session = requests.Session()

            # 1. Initiate the login flow
            flow_resp = session.post(
                f"{HA_URL}/auth/login_flow",
                json={
                    "client_id": f"{HA_URL}/",
                    "handler": ["homeassistant", None],
                    "redirect_uri": f"{HA_URL}/",
                },
                timeout=30,
            )
            flow_resp.raise_for_status()
            flow_id = flow_resp.json()["flow_id"]

            # 2. Submit credentials
            cred_resp = session.post(
                f"{HA_URL}/auth/login_flow/{flow_id}",
                json={
                    "username": HA_USERNAME,
                    "password": HA_PASSWORD,
                    "client_id": f"{HA_URL}/",
                },
                timeout=30,
            )
            cred_resp.raise_for_status()
            cred_data = cred_resp.json()
            if cred_data.get("type") != "create_entry":
                raise RuntimeError(
                    f"Login flow did not complete: type={cred_data.get('type')!r}, "
                    f"errors={cred_data.get('errors')}"
                )
            auth_code = cred_data["result"]

            # 3. Exchange code for token
            token_resp = session.post(
                f"{HA_URL}/auth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "client_id": f"{HA_URL}/",
                },
                timeout=30,
            )
            token_resp.raise_for_status()
            _HA_TOKEN = token_resp.json()["access_token"]
            return _HA_TOKEN
        except Exception as exc:  # noqa: BLE001
            last_exc = exc

    raise RuntimeError(f"Failed to obtain HA token after 5 attempts: {last_exc}") from last_exc


def wait_for_ha(timeout: int = 300) -> None:
    """Block until Home Assistant is fully started and accepts API requests.

    Polls GET /api/onboarding which requires no authentication and therefore
    cannot trigger HA's IP-ban mechanism.  The endpoint returns HTTP 200 even
    during onboarding, so it is safe to use as a startup indicator.
    """
    deadline = time.time() + timeout

    # Phase 1: wait for the web server to respond at all
    while time.time() < deadline:
        try:
            resp = requests.get(f"{HA_URL}/api/onboarding", timeout=5)
            if resp.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(3)
    else:
        raise RuntimeError(f"Home Assistant did not become ready within {timeout}s")

    # Phase 2: small fixed delay to let HA finish loading custom components
    # and installing their requirements (asyncssh etc.) after the web server is up.
    time.sleep(15)


# ---------------------------------------------------------------------------
# Session-scoped Playwright fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    """Provide a session-scoped Playwright instance."""
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Generator[Browser, None, None]:
    """Provide a session-scoped Chromium browser."""
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture(scope="session")
def ha_base_url() -> str:
    """Return the configured Home Assistant base URL."""
    return HA_URL


@pytest.fixture(scope="session")
def ha_token() -> str:
    """Provide a valid Home Assistant long-lived access token."""
    wait_for_ha()
    return get_ha_token()


# ---------------------------------------------------------------------------
# Per-test browser context with an authenticated HA session
# ---------------------------------------------------------------------------


@pytest.fixture()
def context(browser: Browser, ha_token: str) -> Generator[BrowserContext, None, None]:
    """Provide an authenticated browser context for Home Assistant.

    The HA frontend reads ``hassTokens`` from ``localStorage`` to determine
    whether the user is authenticated.  Using Playwright's ``storage_state``
    pre-populates ``localStorage`` *before* the first navigation, which is
    more reliable than ``add_init_script`` (the latter can lose a race with
    HA's own auth-check code and cause a redirect to ``/onboarding.html``).
    """
    hass_tokens = json.dumps({
        "access_token": ha_token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "hassUrl": HA_URL,
        "clientId": f"{HA_URL}/",
        "expires": int(time.time() * 1000) + 1_800_000,
        "refresh_token": "",
    })
    ctx = browser.new_context(
        base_url=HA_URL,
        storage_state={
            "cookies": [],
            "origins": [
                {
                    "origin": HA_URL,
                    "localStorage": [
                        {"name": "hassTokens", "value": hass_tokens},
                    ],
                }
            ],
        },
    )
    yield ctx
    ctx.close()


@pytest.fixture()
def page(context: BrowserContext) -> Generator[Page, None, None]:
    """Provide a fresh page within the authenticated browser context."""
    pg = context.new_page()
    yield pg
    pg.close()


# ---------------------------------------------------------------------------
# Docker host fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def docker_host() -> dict:
    """Return connection parameters for the Docker host.

    The host runs a mock Docker CLI over SSH and pre-populates two containers:
    ``test-app`` and ``test-app-2``.
    """
    return {
        "host": DOCKER_HOST_NAME,
        "username": SSH_USER,
        "password": SSH_PASSWORD,
        "container_1": TEST_CONTAINER_1,
        "container_2": TEST_CONTAINER_2,
    }


# ---------------------------------------------------------------------------
# HA API session fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def ha_api(ha_token: str) -> requests.Session:
    """Return a requests Session pre-configured to call the HA REST API."""
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {ha_token}"
    session.headers["Content-Type"] = "application/json"
    return session


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_ssh_docker_entry_ids(ha_api: requests.Session) -> list[dict]:
    """Return all current ssh_docker config entries."""
    resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
    resp.raise_for_status()
    return [e for e in resp.json() if e.get("domain") == "ssh_docker"]


def _remove_all_ssh_docker_entries(ha_api: requests.Session) -> None:
    """Delete every ssh_docker config entry from Home Assistant."""
    for entry in _get_ssh_docker_entry_ids(ha_api):
        ha_api.delete(f"{HA_URL}/api/config/config_entries/entry/{entry['entry_id']}")


def _add_ssh_docker_entry(
    ha_api: requests.Session,
    name: str,
    container: str,
    host: str,
    username: str,
    password: str,
) -> dict:
    """Add a new ssh_docker config entry via the config flow API.

    Returns the completed flow response dict (type == 'create_entry' on success).
    """
    # Step 1: initiate the flow
    flow_resp = ha_api.post(
        f"{HA_URL}/api/config/config_entries/flow",
        json={"handler": "ssh_docker"},
    )
    flow_resp.raise_for_status()
    flow_id = flow_resp.json()["flow_id"]

    # Step 2: submit the user form
    entry_resp = ha_api.post(
        f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
        json={
            "name": name,
            "service": container,
            "host": host,
            "username": username,
            "password": password,
            "check_known_hosts": False,
            "docker_command": "docker",
            "check_for_updates": False,
            "auto_update": False,
        },
    )
    entry_resp.raise_for_status()
    return entry_resp.json()


# ---------------------------------------------------------------------------
# Integration setup / teardown helper
# ---------------------------------------------------------------------------


@pytest.fixture()
def ensure_integration(ha_api: requests.Session, docker_host: dict) -> Generator[str, None, None]:
    """Ensure one ssh_docker entry (test-app on docker_host) is present.

    Yields the config entry ID.  After the test the entry is removed so that
    every test run starts from the same baseline.
    """
    # Remove any leftover entries from previous runs
    _remove_all_ssh_docker_entries(ha_api)

    result = _add_ssh_docker_entry(
        ha_api,
        name="Test App",
        container=docker_host["container_1"],
        host=docker_host["host"],
        username=docker_host["username"],
        password=docker_host["password"],
    )
    assert result.get("type") == "create_entry", (
        f"Config flow did not return create_entry: {result}"
    )

    # Find the new entry
    entries = _get_ssh_docker_entry_ids(ha_api)
    assert len(entries) == 1, f"Expected 1 ssh_docker entry, found {len(entries)}"
    entry_id = entries[0]["entry_id"]

    # Wait for HA to create the sensor entity AND for the initial SSH fetch
    # (docker inspect + docker_create availability check) to complete.
    # A fixed sleep is unreliable in CI because each SSH call can take 1-3 s;
    # poll instead until the entity exists and is in a non-transitional state.
    _TRANSITIONAL = {
        "initializing", "stopping", "starting", "creating",
        "recreating", "removing", "refreshing",
    }
    _deadline = time.time() + 60
    while time.time() < _deadline:
        _resp = ha_api.get(f"{HA_URL}/api/states")
        if _resp.status_code == 200:
            _entity = next(
                (s for s in _resp.json() if s["entity_id"].startswith("sensor.ssh_docker_")),
                None,
            )
            if _entity and _entity.get("state") not in _TRANSITIONAL:
                break
        time.sleep(2)

    yield entry_id

    # --- Teardown ---
    ha_api.delete(f"{HA_URL}/api/config/config_entries/entry/{entry_id}")

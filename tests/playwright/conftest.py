"""Shared fixtures for SSH Docker Playwright end-to-end tests.

Environment variables (with defaults):
    HOMEASSISTANT_URL   – base URL of the HA instance (default: http://homeassistant:8123)
    HA_USERNAME         – HA owner username created during onboarding (default: admin)
    HA_PASSWORD         – HA owner password (default: adminpassword)
    SSH_HOST            – hostname / IP of the Docker-in-Docker SSH target (default: ssh_docker_test)
    DOCKER_SSH_PORT     – SSH port on the Docker host (default: 22)
    DOCKER_SSH_USER     – SSH username (default: root)
    DOCKER_SSH_PASSWORD – SSH password (default: testpassword)
"""

from __future__ import annotations

import os
import time
from typing import Generator

import pytest
import requests
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# ---------------------------------------------------------------------------
# Environment-variable defaults
# ---------------------------------------------------------------------------

HA_URL: str = os.environ.get("HOMEASSISTANT_URL", "http://homeassistant:8123")
HA_USERNAME: str = os.environ.get("HA_USERNAME", "admin")
HA_PASSWORD: str = os.environ.get("HA_PASSWORD", "adminpassword")

SSH_HOST: str = os.environ.get("SSH_HOST", "ssh_docker_test")
DOCKER_SSH_PORT: int = int(os.environ.get("DOCKER_SSH_PORT", "22"))
DOCKER_SSH_USER: str = os.environ.get("DOCKER_SSH_USER", "root")
DOCKER_SSH_PASSWORD: str = os.environ.get("DOCKER_SSH_PASSWORD", "testpassword")

INTEGRATION_DOMAIN = "ssh_docker"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_ha(timeout: int = 120) -> None:
    """Block until Home Assistant responds to HTTP requests."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{HA_URL}/api/", timeout=5)
            if r.status_code in (200, 401):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError(f"Home Assistant did not become available within {timeout}s")


def _get_ha_token() -> str:
    """Obtain a long-lived access token from Home Assistant via the REST API.

    Uses the onboarding flow when no users exist, otherwise authenticates with
    the configured credentials.
    """
    # Try existing credentials first
    auth_url = f"{HA_URL}/auth/token"
    resp = requests.post(
        auth_url,
        data={
            "grant_type": "password",
            "username": HA_USERNAME,
            "password": HA_PASSWORD,
            "client_id": HA_URL,
        },
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()["access_token"]

    raise RuntimeError(
        f"Could not obtain HA token (status {resp.status_code}). "
        "Ensure the HA instance is onboarded and credentials are correct."
    )


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ha_url() -> str:
    """Return the Home Assistant base URL."""
    return HA_URL


@pytest.fixture(scope="session")
def ha_token() -> str:
    """Return a long-lived access token for the HA REST API."""
    _wait_for_ha()
    return _get_ha_token()


@pytest.fixture(scope="session")
def ha_api_session(ha_token: str) -> requests.Session:
    """Return a pre-authenticated requests.Session for the HA REST API."""
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {ha_token}"})
    return session


@pytest.fixture(scope="session")
def ssh_config() -> dict:
    """Return SSH connection parameters for the Docker host."""
    return {
        "host": SSH_HOST,
        "port": DOCKER_SSH_PORT,
        "username": DOCKER_SSH_USER,
        "password": DOCKER_SSH_PASSWORD,
    }


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    """Start and stop the Playwright engine for the whole test session."""
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Generator[Browser, None, None]:
    """Launch a headless Chromium browser for the test session."""
    br = playwright_instance.chromium.launch(headless=True)
    yield br
    br.close()


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def browser_context(browser: Browser, ha_url: str, ha_token: str) -> Generator[BrowserContext, None, None]:
    """Create a new browser context with a pre-authenticated HA session cookie."""
    context = browser.new_context(base_url=ha_url)
    # Inject the token so HA Lovelace recognises the session immediately
    context.add_init_script(
        f"window.__tokenInjected = true; "
        f"localStorage.setItem('hassTokens', JSON.stringify({{"
        f"  'access_token': '{ha_token}',"
        f"  'token_type': 'Bearer',"
        f"  'expires_in': 1800,"
        f"  'hassUrl': '{ha_url}',"
        f"  'clientId': '{ha_url}/',"
        f"  'expires': Date.now() + 1800000,"
        f"  'refresh_token': ''"
        f"}}))"
    )
    yield context
    context.close()


@pytest.fixture()
def page(browser_context: BrowserContext) -> Generator[Page, None, None]:
    """Open a new page in the authenticated browser context."""
    pg = browser_context.new_page()
    yield pg
    pg.close()


# ---------------------------------------------------------------------------
# Integration setup / teardown helpers
# ---------------------------------------------------------------------------

def _delete_integration_entries(session: requests.Session) -> None:
    """Remove all ssh_docker config entries via the HA REST API."""
    resp = session.get(f"{HA_URL}/api/config/config_entries/entry", timeout=10)
    if resp.status_code != 200:
        return
    for entry in resp.json():
        if entry.get("domain") == INTEGRATION_DOMAIN:
            session.delete(
                f"{HA_URL}/api/config/config_entries/entry/{entry['entry_id']}",
                timeout=10,
            )


@pytest.fixture()
def clean_integration(ha_api_session: requests.Session) -> Generator[None, None, None]:
    """Ensure no ssh_docker entries exist before and after the test."""
    _delete_integration_entries(ha_api_session)
    yield
    _delete_integration_entries(ha_api_session)


@pytest.fixture()
def integration_entry_id(ha_api_session: requests.Session) -> Generator[str, None, None]:
    """Set up an ssh_docker integration entry and return its entry_id.

    Creates the entry through the HA REST API config-flow endpoint so tests
    start with a live integration.  Removes the entry after the test.
    """
    # Step 1: Initiate config flow
    init_resp = ha_api_session.post(
        f"{HA_URL}/api/config/config_entries/flow",
        json={"handler": INTEGRATION_DOMAIN},
        timeout=10,
    )
    assert init_resp.status_code == 200, f"Failed to init config flow: {init_resp.text}"
    flow_id = init_resp.json()["flow_id"]

    # Step 2: Submit connection details
    submit_resp = ha_api_session.post(
        f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
        json={
            "name": "e2e_test_container",
            "service": "ssh_test_1",
            "host": SSH_HOST,
            "username": DOCKER_SSH_USER,
            "password": DOCKER_SSH_PASSWORD,
            "check_known_hosts": False,
            "check_for_updates": False,
            "auto_update": False,
        },
        timeout=30,
    )
    data = submit_resp.json()
    assert data.get("type") in ("create_entry", "result"), (
        f"Config flow did not create entry: {data}"
    )
    entry_id = data.get("entry_id") or data.get("result", {}).get("entry_id")
    assert entry_id, f"No entry_id in config flow result: {data}"

    yield entry_id

    # Teardown – remove the entry
    ha_api_session.delete(
        f"{HA_URL}/api/config/config_entries/entry/{entry_id}",
        timeout=10,
    )

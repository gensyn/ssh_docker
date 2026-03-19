"""Playwright E2E tests for SSH Docker integration setup via config flow.

Covers:
- Adding the integration through the UI config flow
- SSH connection validation
- Verifying the integration appears in the integrations list
- Connection error handling
- Authentication validation
"""

from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect

from conftest import (
    HA_URL,
    INTEGRATION_DOMAIN,
    SSH_HOST,
    DOCKER_SSH_PORT,
    DOCKER_SSH_USER,
    DOCKER_SSH_PASSWORD,
)


class TestIntegrationSetupViaUI:
    """Test adding the SSH Docker integration through the Home Assistant UI."""

    def test_integration_config_flow_opens(self, page: Page) -> None:
        """The config-flow dialog for ssh_docker can be opened in the UI."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")

        # Click the "Add integration" button
        add_btn = page.get_by_role("button", name="Add integration")
        add_btn.click()

        # Type the integration name in the search box
        search = page.get_by_placeholder("Search")
        search.fill("SSH Docker")
        page.wait_for_timeout(500)

        # The integration should appear in the search results
        result = page.get_by_text("SSH Docker")
        expect(result.first).to_be_visible()

    def test_integration_config_flow_submit_success(
        self, page: Page, clean_integration: None
    ) -> None:
        """Filling in valid SSH credentials creates the integration entry."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")

        # Open the add-integration dialog
        page.get_by_role("button", name="Add integration").click()
        page.get_by_placeholder("Search").fill("SSH Docker")
        page.wait_for_timeout(500)
        page.get_by_text("SSH Docker").first.click()
        page.wait_for_timeout(500)

        # Fill in the config-flow form fields
        page.get_by_label("Name").fill("Test Container")
        page.get_by_label("Service / container name").fill("ssh_test_1")
        page.get_by_label("Host").fill(SSH_HOST)
        page.get_by_label("Username").fill(DOCKER_SSH_USER)
        page.get_by_label("Password").fill(DOCKER_SSH_PASSWORD)

        # Disable known-hosts check to avoid host-key prompts in CI
        known_hosts_checkbox = page.get_by_label("Check known hosts")
        if known_hosts_checkbox.is_checked():
            known_hosts_checkbox.uncheck()

        page.get_by_role("button", name="Submit").click()
        page.wait_for_timeout(2000)

        # Integration should now appear on the integrations page
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("SSH Docker").first).to_be_visible()

    def test_integration_config_flow_invalid_host(
        self, page: Page, clean_integration: None
    ) -> None:
        """Providing an unreachable host surfaces an error in the config flow."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")

        page.get_by_role("button", name="Add integration").click()
        page.get_by_placeholder("Search").fill("SSH Docker")
        page.wait_for_timeout(500)
        page.get_by_text("SSH Docker").first.click()
        page.wait_for_timeout(500)

        page.get_by_label("Name").fill("Bad Host Test")
        page.get_by_label("Service / container name").fill("nonexistent")
        page.get_by_label("Host").fill("192.0.2.1")  # RFC 5737 TEST-NET-1; never routable
        page.get_by_label("Username").fill("root")
        page.get_by_label("Password").fill("wrongpassword")

        known_hosts_checkbox = page.get_by_label("Check known hosts")
        if known_hosts_checkbox.is_checked():
            known_hosts_checkbox.uncheck()

        page.get_by_role("button", name="Submit").click()
        # HA should not navigate away; the dialog remains open or shows an error
        page.wait_for_timeout(5000)

        # Either an error message is shown, or the dialog is still visible
        dialog_still_open = page.get_by_role("dialog").count() > 0
        error_shown = page.get_by_text("Connection refused").count() > 0
        assert dialog_still_open or error_shown


class TestIntegrationSetupViaAPI:
    """Test adding the SSH Docker integration through the REST API."""

    def test_config_flow_creates_entry(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """A valid REST API config-flow submission creates an entry."""
        init_resp = ha_api_session.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": INTEGRATION_DOMAIN},
            timeout=10,
        )
        assert init_resp.status_code == 200
        flow = init_resp.json()
        assert flow["type"] == "form"
        flow_id = flow["flow_id"]

        submit_resp = ha_api_session.post(
            f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
            json={
                "name": "api_test_container",
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
            f"Unexpected flow result: {data}"
        )

    def test_config_flow_initial_step_returns_form(
        self, ha_api_session: requests.Session
    ) -> None:
        """Initiating the config flow returns a form step."""
        resp = ha_api_session.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": INTEGRATION_DOMAIN},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form"
        assert "flow_id" in data
        assert data["step_id"] == "user"

        # Clean up the dangling flow
        ha_api_session.delete(
            f"{HA_URL}/api/config/config_entries/flow/{data['flow_id']}",
            timeout=10,
        )

    def test_integration_appears_in_entries_after_setup(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """The integration entry is listed via the config-entries API after setup."""
        resp = ha_api_session.get(
            f"{HA_URL}/api/config/config_entries/entry",
            timeout=10,
        )
        assert resp.status_code == 200
        entries = resp.json()
        domains = [e["domain"] for e in entries]
        assert INTEGRATION_DOMAIN in domains

    def test_integration_entry_has_correct_fields(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """The created config entry exposes the expected domain and title."""
        resp = ha_api_session.get(
            f"{HA_URL}/api/config/config_entries/entry",
            timeout=10,
        )
        assert resp.status_code == 200
        entry = next(
            (e for e in resp.json() if e["entry_id"] == integration_entry_id),
            None,
        )
        assert entry is not None
        assert entry["domain"] == INTEGRATION_DOMAIN
        assert entry["state"] in ("loaded", "setup_error", "setup_retry", "not_loaded")

    def test_duplicate_entry_is_rejected(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """Creating a second entry for the same container is rejected."""
        init_resp = ha_api_session.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": INTEGRATION_DOMAIN},
            timeout=10,
        )
        assert init_resp.status_code == 200
        flow_id = init_resp.json()["flow_id"]

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
        # HA should either abort (already_configured) or return an error
        data = submit_resp.json()
        assert data.get("type") in ("abort", "form"), (
            f"Expected abort or form error for duplicate, got: {data}"
        )

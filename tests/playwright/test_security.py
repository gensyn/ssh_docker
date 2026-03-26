"""Playwright E2E tests: SSH Docker security properties."""

from __future__ import annotations

import requests

from conftest import (
    HA_URL,
    DOCKER_HOST_NAME,
    SSH_USER,
    _remove_all_ssh_docker_entries,
    _get_ssh_docker_entry_ids,
)


class TestSecurity:
    """Tests that validate the security properties of the SSH Docker integration."""

    def test_api_requires_authentication(self) -> None:
        """Calling the HA service API without an auth token is rejected with 401."""
        resp = requests.get(
            f"{HA_URL}/api/states",
            timeout=10,
        )
        assert resp.status_code == 401, resp.text

    def test_service_api_requires_authentication(self) -> None:
        """Calling a service without an auth token returns 401."""
        resp = requests.post(
            f"{HA_URL}/api/services/ssh_docker/refresh",
            json={"entity_id": "sensor.ssh_docker_test_app"},
            timeout=10,
        )
        assert resp.status_code == 401, resp.text

    def test_config_entries_api_requires_authentication(self) -> None:
        """The config entries API requires authentication."""
        resp = requests.get(
            f"{HA_URL}/api/config/config_entries/entry",
            timeout=10,
        )
        assert resp.status_code == 401, resp.text

    def test_invalid_credentials_rejected_at_config_flow(
        self, ha_api: requests.Session
    ) -> None:
        """Invalid SSH credentials cause the config flow to return an error."""
        _remove_all_ssh_docker_entries(ha_api)

        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_docker"},
        )
        flow_resp.raise_for_status()
        flow_id = flow_resp.json()["flow_id"]

        resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
            json={
                "name": "Invalid Creds",
                "service": "test-app",
                "host": DOCKER_HOST_NAME,
                "username": SSH_USER,
                "password": "invalid_password_that_will_never_work_xyz",
                "check_known_hosts": False,
                "docker_command": "docker",
                "check_for_updates": False,
                "auto_update": False,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        assert result.get("type") == "form", (
            f"Expected form (auth error) for invalid credentials, got: {result.get('type')!r}"
        )
        assert result.get("errors"), "Expected non-empty errors for invalid credentials"

    def test_unreachable_host_rejected(self, ha_api: requests.Session) -> None:
        """Connecting to an unreachable host returns an error during config flow."""
        _remove_all_ssh_docker_entries(ha_api)

        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_docker"},
        )
        flow_resp.raise_for_status()
        flow_id = flow_resp.json()["flow_id"]

        resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
            json={
                "name": "Unreachable",
                "service": "test-app",
                "host": "192.0.2.255",  # RFC 5737 TEST-NET
                "username": "user",
                "password": "pass",
                "check_known_hosts": False,
                "docker_command": "docker",
                "check_for_updates": False,
                "auto_update": False,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        assert result.get("type") in ("form", "abort"), (
            f"Expected form/abort for unreachable host, got: {result.get('type')!r}"
        )

    def test_no_credentials_rejected(self, ha_api: requests.Session) -> None:
        """Submitting without password or key_file returns a validation error."""
        _remove_all_ssh_docker_entries(ha_api)

        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_docker"},
        )
        flow_resp.raise_for_status()
        flow_id = flow_resp.json()["flow_id"]

        resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
            json={
                "name": "No Creds",
                "service": "test-app",
                "host": DOCKER_HOST_NAME,
                "username": SSH_USER,
                "check_known_hosts": False,
                "docker_command": "docker",
                "check_for_updates": False,
                "auto_update": False,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        assert result.get("type") == "form", (
            f"Expected form (validation error) without credentials, got: {result.get('type')!r}"
        )
        assert result.get("errors"), "Expected errors for missing credentials"

    def test_service_call_with_nonexistent_entity_returns_error(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """A service call referencing a nonexistent entity returns 400+."""
        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/refresh",
            json={"entity_id": "sensor.nonexistent_entity_that_does_not_exist"},
        )
        assert resp.status_code >= 400, (
            f"Expected error for nonexistent entity, got {resp.status_code}"
        )

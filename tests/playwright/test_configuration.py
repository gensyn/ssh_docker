"""Playwright E2E tests: SSH Docker configuration management."""

from __future__ import annotations

import requests

from conftest import (
    HA_URL,
    DOCKER_HOST_NAME,
    SSH_USER,
    SSH_PASSWORD,
    _remove_all_ssh_docker_entries,
    _add_ssh_docker_entry,
    _get_ssh_docker_entry_ids,
)


class TestConfiguration:
    """Tests covering configuration options of the SSH Docker integration."""

    def test_password_auth_accepted(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """Password-based authentication is accepted and the entry is created."""
        # The ensure_integration fixture uses password auth — verify the entry exists
        entries = _get_ssh_docker_entry_ids(ha_api)
        assert len(entries) == 1, "Expected exactly 1 ssh_docker entry with password auth"

    def test_missing_auth_rejected(self, ha_api: requests.Session) -> None:
        """Submitting the config form without password or key_file is rejected."""
        _remove_all_ssh_docker_entries(ha_api)

        # Start flow
        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_docker"},
        )
        flow_resp.raise_for_status()
        flow_id = flow_resp.json()["flow_id"]

        # Submit without any auth credentials
        resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
            json={
                "name": "No Auth",
                "service": "test-app",
                "host": DOCKER_HOST_NAME,
                "username": SSH_USER,
                # neither password nor key_file
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
        assert result.get("errors"), "Expected errors dict to be non-empty"

    def test_invalid_password_rejected(self, ha_api: requests.Session) -> None:
        """Wrong password returns a config flow error (cannot connect)."""
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
                "name": "Bad Pass",
                "service": "test-app",
                "host": DOCKER_HOST_NAME,
                "username": SSH_USER,
                "password": "definitely_wrong_password_xyz",
                "check_known_hosts": False,
                "docker_command": "docker",
                "check_for_updates": False,
                "auto_update": False,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        assert result.get("type") == "form", (
            f"Expected form (error) for wrong password, got: {result.get('type')!r}"
        )
        assert result.get("errors"), "Expected errors for wrong password"

    def test_multiple_entries_independent(self, ha_api: requests.Session) -> None:
        """Multiple ssh_docker entries (different containers) can coexist."""
        _remove_all_ssh_docker_entries(ha_api)

        # Add first entry
        r1 = _add_ssh_docker_entry(
            ha_api,
            name="Test App 1",
            container="test-app",
            host=DOCKER_HOST_NAME,
            username=SSH_USER,
            password=SSH_PASSWORD,
        )
        assert r1.get("type") == "create_entry", f"Entry 1 failed: {r1}"

        # Add second entry (different container, different name)
        r2 = _add_ssh_docker_entry(
            ha_api,
            name="Test App 2",
            container="test-app-2",
            host=DOCKER_HOST_NAME,
            username=SSH_USER,
            password=SSH_PASSWORD,
        )
        assert r2.get("type") == "create_entry", f"Entry 2 failed: {r2}"

        entries = _get_ssh_docker_entry_ids(ha_api)
        assert len(entries) == 2, (
            f"Expected 2 independent ssh_docker entries, found {len(entries)}"
        )

        # Teardown
        _remove_all_ssh_docker_entries(ha_api)

    def test_check_known_hosts_false_accepted(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """check_known_hosts=False is accepted and leads to a successful entry."""
        entries = _get_ssh_docker_entry_ids(ha_api)
        assert any(e["domain"] == "ssh_docker" for e in entries), (
            "Expected at least one ssh_docker entry with check_known_hosts=False"
        )

    def test_nonexistent_host_rejected(self, ha_api: requests.Session) -> None:
        """A non-existent hostname causes the config flow to return an error."""
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
                "name": "Bad Host",
                "service": "test-app",
                "host": "this.host.does.not.exist.invalid",
                "username": SSH_USER,
                "password": SSH_PASSWORD,
                "check_known_hosts": False,
                "docker_command": "docker",
                "check_for_updates": False,
                "auto_update": False,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        assert result.get("type") in ("form", "abort"), (
            f"Expected form/abort for non-existent host, got: {result.get('type')!r}"
        )

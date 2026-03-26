"""Playwright E2E tests: SSH Docker integration setup via the config flow."""

from __future__ import annotations

from typing import Any

import requests

from conftest import (
    HA_URL,
    DOCKER_HOST_NAME,
    SSH_USER,
    SSH_PASSWORD,
    _get_ssh_docker_entry_ids,
    _remove_all_ssh_docker_entries,
    _add_ssh_docker_entry,
)


class TestIntegrationSetup:
    """Tests that cover adding and removing the SSH Docker integration."""

    def test_connection_error_with_unreachable_host(self, ha_api: requests.Session) -> None:
        """Attempting to add an integration with an unreachable host returns an error."""
        # Clean slate
        _remove_all_ssh_docker_entries(ha_api)

        # Start the config flow
        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_docker"},
        )
        flow_resp.raise_for_status()
        flow_id = flow_resp.json()["flow_id"]

        # Submit with a guaranteed-unreachable host
        entry_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
            json={
                "name": "Unreachable",
                "service": "test-app",
                "host": "192.0.2.1",  # RFC 5737 TEST-NET
                "username": "nobody",
                "password": "nopass",
                "check_known_hosts": False,
                "docker_command": "docker",
                "check_for_updates": False,
                "auto_update": False,
            },
        )
        entry_resp.raise_for_status()
        result = entry_resp.json()
        # Expect a form re-display with an error, not a created entry
        assert result.get("type") in ("form", "abort"), (
            f"Expected 'form' or 'abort' on unreachable host, got: {result.get('type')!r}"
        )
        if result.get("type") == "form":
            assert result.get("errors"), "Expected errors dict to be non-empty"

    def test_duplicate_name_rejected(self, ha_api: requests.Session, ensure_integration: str) -> None:
        """Adding a second entry with the same container name is rejected."""
        # The fixture already created an entry; try adding one with the same name
        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_docker"},
        )
        flow_resp.raise_for_status()
        flow_id = flow_resp.json()["flow_id"]

        entry_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
            json={
                "name": "Test App",  # duplicate name
                "service": "test-app",
                "host": DOCKER_HOST_NAME,
                "username": SSH_USER,
                "password": SSH_PASSWORD,
                "check_known_hosts": False,
                "docker_command": "docker",
                "check_for_updates": False,
                "auto_update": False,
            },
        )
        entry_resp.raise_for_status()
        result = entry_resp.json()
        # HA should return a form error or abort for duplicate
        assert result.get("type") in ("form", "abort"), (
            f"Expected 'form' or 'abort' for duplicate name, got: {result.get('type')!r}"
        )


class TestIntegrationLifecycle:
    """Full add → use → remove lifecycle test."""

    def test_full_lifecycle(self, ha_api: requests.Session, docker_host: Any) -> None:
        """Complete add → inspect → remove lifecycle for an ssh_docker entry."""

        # ------------------------------------------------------------------ #
        # 0. Clean state                                                      #
        # ------------------------------------------------------------------ #
        _remove_all_ssh_docker_entries(ha_api)
        assert _get_ssh_docker_entry_ids(ha_api) == [], (
            "Precondition failed: ssh_docker entries still present after cleanup"
        )

        # ------------------------------------------------------------------ #
        # 1. Add the integration                                              #
        # ------------------------------------------------------------------ #
        result = _add_ssh_docker_entry(
            ha_api,
            name="Test App",
            container=docker_host["container_1"],
            host=docker_host["host"],
            username=docker_host["username"],
            password=docker_host["password"],
        )
        assert result.get("type") == "create_entry", (
            f"Expected 'create_entry', got: {result.get('type')!r}"
        )

        entries = _get_ssh_docker_entry_ids(ha_api)
        assert len(entries) == 1, (
            f"Expected exactly 1 ssh_docker entry, found: {len(entries)}"
        )
        entry_id = entries[0]["entry_id"]

        # ------------------------------------------------------------------ #
        # 2. Verify it appears in the entries list                            #
        # ------------------------------------------------------------------ #
        all_entries = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
        all_entries.raise_for_status()
        matching = [e for e in all_entries.json() if e["entry_id"] == entry_id]
        assert len(matching) == 1
        assert matching[0]["domain"] == "ssh_docker"

        # ------------------------------------------------------------------ #
        # 3. Adding a second entry with the same unique ID is rejected        #
        # ------------------------------------------------------------------ #
        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_docker"},
        )
        flow_resp.raise_for_status()
        flow_id = flow_resp.json()["flow_id"]

        dup_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
            json={
                "name": "Test App Duplicate",
                "service": docker_host["container_1"],  # same host+service → same unique ID
                "host": docker_host["host"],
                "username": docker_host["username"],
                "password": docker_host["password"],
                "check_known_hosts": False,
                "docker_command": "docker",
                "check_for_updates": False,
                "auto_update": False,
            },
        )
        dup_resp.raise_for_status()
        dup_result = dup_resp.json()
        assert dup_result.get("type") in ("form", "abort"), (
            f"Expected form/abort for duplicate host+service, got: {dup_result.get('type')!r}"
        )
        # Still only one entry
        assert len(_get_ssh_docker_entry_ids(ha_api)) == 1

        # ------------------------------------------------------------------ #
        # 4. Remove the integration                                           #
        # ------------------------------------------------------------------ #
        del_resp = ha_api.delete(
            f"{HA_URL}/api/config/config_entries/entry/{entry_id}"
        )
        assert del_resp.status_code in (200, 204), del_resp.text

        # ------------------------------------------------------------------ #
        # 5. Environment is clean after removal                               #
        # ------------------------------------------------------------------ #
        assert _get_ssh_docker_entry_ids(ha_api) == [], (
            "ssh_docker entries still present after removal"
        )

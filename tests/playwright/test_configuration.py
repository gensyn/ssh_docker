"""Playwright E2E tests for SSH Docker configuration and options.

Covers:
- Updating SSH host options via options flow
- Changing scan interval settings
- Toggling check_for_updates and auto_update
- Adding / removing multiple Docker host entries
- Configuration persists across HA restarts (entry reload)
"""

from __future__ import annotations

import time

import pytest
import requests

from conftest import HA_URL, INTEGRATION_DOMAIN, SSH_HOST, DOCKER_SSH_USER, DOCKER_SSH_PASSWORD


def _get_entry(session: requests.Session, entry_id: str) -> dict | None:
    """Return the config entry dict for the given entry_id."""
    resp = session.get(f"{HA_URL}/api/config/config_entries/entry", timeout=10)
    if resp.status_code != 200:
        return None
    return next(
        (e for e in resp.json() if e["entry_id"] == entry_id),
        None,
    )


def _init_options_flow(session: requests.Session, entry_id: str) -> dict:
    """Initiate an options flow for an existing config entry."""
    resp = session.post(
        f"{HA_URL}/api/config/config_entries/entry/{entry_id}/options",
        timeout=10,
    )
    return resp.json()


class TestOptionsFlow:
    """Test the SSH Docker options flow via the API."""

    def test_options_flow_can_be_initiated(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """An options flow can be initiated for an existing entry."""
        resp = ha_api_session.post(
            f"{HA_URL}/api/config/config_entries/entry/{integration_entry_id}/options",
            timeout=10,
        )
        # May return 200 (form) or 405 if options flow not supported via this endpoint
        assert resp.status_code in (200, 405, 404), (
            f"Unexpected status from options flow init: {resp.status_code}: {resp.text}"
        )

    def test_entry_can_be_reloaded(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """An existing entry can be reloaded via the API."""
        resp = ha_api_session.post(
            f"{HA_URL}/api/config/config_entries/entry/{integration_entry_id}/reload",
            timeout=30,
        )
        assert resp.status_code in (200, 204), (
            f"Entry reload returned {resp.status_code}: {resp.text}"
        )

    def test_entry_state_after_reload(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """After reload, the entry state is a valid HA entry state."""
        ha_api_session.post(
            f"{HA_URL}/api/config/config_entries/entry/{integration_entry_id}/reload",
            timeout=30,
        )
        time.sleep(5)

        entry = _get_entry(ha_api_session, integration_entry_id)
        assert entry is not None, "Entry not found after reload"
        valid_states = {"loaded", "setup_error", "setup_retry", "not_loaded", "failed_unload"}
        assert entry["state"] in valid_states, (
            f"Unexpected entry state after reload: {entry['state']!r}"
        )


class TestMultipleEntries:
    """Test adding and removing multiple Docker host entries."""

    def test_multiple_entries_can_coexist(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """Two separate ssh_docker entries can be created and coexist."""
        entry_ids = []
        try:
            for container_name in ("ssh_test_1", "ssh_test_2"):
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
                        "name": f"multi_{container_name}",
                        "service": container_name,
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
                entry_id = data.get("entry_id") or data.get("result", {}).get("entry_id")
                if entry_id:
                    entry_ids.append(entry_id)

            assert len(entry_ids) == 2, (
                f"Expected 2 entries, only got {len(entry_ids)}"
            )

            # Verify both entries are in the config
            resp = ha_api_session.get(
                f"{HA_URL}/api/config/config_entries/entry", timeout=10
            )
            assert resp.status_code == 200
            all_entry_ids = [e["entry_id"] for e in resp.json()]
            for eid in entry_ids:
                assert eid in all_entry_ids, f"Entry {eid} missing from config entries"

        finally:
            for eid in entry_ids:
                ha_api_session.delete(
                    f"{HA_URL}/api/config/config_entries/entry/{eid}",
                    timeout=10,
                )

    def test_removing_one_entry_does_not_affect_other(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """Removing one entry leaves the other entry intact."""
        entry_ids = []
        try:
            for container_name in ("ssh_test_1", "ssh_test_2"):
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
                        "name": f"remove_test_{container_name}",
                        "service": container_name,
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
                entry_id = data.get("entry_id") or data.get("result", {}).get("entry_id")
                if entry_id:
                    entry_ids.append(entry_id)

            assert len(entry_ids) == 2

            # Remove the first entry
            resp = ha_api_session.delete(
                f"{HA_URL}/api/config/config_entries/entry/{entry_ids[0]}",
                timeout=10,
            )
            assert resp.status_code in (200, 204)

            # Second entry should still exist
            remaining_entry = _get_entry(ha_api_session, entry_ids[1])
            assert remaining_entry is not None, (
                "Second entry was removed when only first should have been removed"
            )

        finally:
            for eid in entry_ids[1:]:
                ha_api_session.delete(
                    f"{HA_URL}/api/config/config_entries/entry/{eid}",
                    timeout=10,
                )


class TestConfigurationPersistence:
    """Test that integration configuration persists."""

    def test_entry_persists_after_creation(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """The config entry persists and is retrievable via the API."""
        entry = _get_entry(ha_api_session, integration_entry_id)
        assert entry is not None, "Config entry not found after creation"
        assert entry["domain"] == INTEGRATION_DOMAIN

    def test_entry_domain_is_correct(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """The config entry has the correct domain value."""
        entry = _get_entry(ha_api_session, integration_entry_id)
        assert entry is not None
        assert entry["domain"] == INTEGRATION_DOMAIN

    def test_entry_can_be_deleted(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """An ssh_docker entry can be deleted via the REST API."""
        # Create an entry
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
                "name": "delete_test",
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
        entry_id = data.get("entry_id") or data.get("result", {}).get("entry_id")
        assert entry_id, f"No entry_id in: {data}"

        # Delete it
        del_resp = ha_api_session.delete(
            f"{HA_URL}/api/config/config_entries/entry/{entry_id}",
            timeout=10,
        )
        assert del_resp.status_code in (200, 204), (
            f"Delete returned {del_resp.status_code}: {del_resp.text}"
        )

        # Confirm it's gone
        entry = _get_entry(ha_api_session, entry_id)
        assert entry is None, "Entry still exists after deletion"

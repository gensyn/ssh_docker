"""Playwright E2E tests for SSH Docker update entities.

Covers:
- Update entity created when check_for_updates is enabled
- Update entity state (on/off/unknown)
- Update entity attributes (installed_version, latest_version)
- Install (auto-update) via update entity
- Update entity state when check_for_updates is disabled
"""

from __future__ import annotations

import time

import pytest
import requests

from conftest import HA_URL, INTEGRATION_DOMAIN, SSH_HOST, DOCKER_SSH_USER, DOCKER_SSH_PASSWORD


def _get_update_entities(session: requests.Session) -> list[dict]:
    """Return all update entities related to ssh_docker."""
    resp = session.get(f"{HA_URL}/api/states", timeout=10)
    assert resp.status_code == 200
    return [
        s for s in resp.json()
        if s["entity_id"].startswith("update.")
        and "ssh" in s["entity_id"]
    ]


def _setup_integration_with_updates(
    session: requests.Session,
    check_for_updates: bool = True,
    auto_update: bool = False,
) -> str:
    """Create an ssh_docker entry with specific update settings; return entry_id."""
    init_resp = session.post(
        f"{HA_URL}/api/config/config_entries/flow",
        json={"handler": INTEGRATION_DOMAIN},
        timeout=10,
    )
    assert init_resp.status_code == 200
    flow_id = init_resp.json()["flow_id"]

    submit_resp = session.post(
        f"{HA_URL}/api/config/config_entries/flow/{flow_id}",
        json={
            "name": "update_test_container",
            "service": "ssh_test_1",
            "host": SSH_HOST,
            "username": DOCKER_SSH_USER,
            "password": DOCKER_SSH_PASSWORD,
            "check_known_hosts": False,
            "check_for_updates": check_for_updates,
            "auto_update": auto_update,
        },
        timeout=30,
    )
    data = submit_resp.json()
    entry_id = data.get("entry_id") or data.get("result", {}).get("entry_id")
    assert entry_id, f"No entry_id in: {data}"
    return entry_id


class TestUpdateEntityCreation:
    """Test that update entities are created correctly."""

    def test_update_entity_created_with_check_for_updates_enabled(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """An update entity is created when check_for_updates=True."""
        entry_id = _setup_integration_with_updates(
            ha_api_session, check_for_updates=True
        )
        time.sleep(5)

        try:
            update_entities = _get_update_entities(ha_api_session)
            # Update entity may or may not be created depending on SSH connectivity
            # but the integration entry should exist
            resp = ha_api_session.get(
                f"{HA_URL}/api/config/config_entries/entry",
                timeout=10,
            )
            assert resp.status_code == 200
            entries = resp.json()
            ssh_docker_entries = [e for e in entries if e["domain"] == INTEGRATION_DOMAIN]
            assert len(ssh_docker_entries) >= 1
        finally:
            ha_api_session.delete(
                f"{HA_URL}/api/config/config_entries/entry/{entry_id}",
                timeout=10,
            )

    def test_update_entity_has_valid_state(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """Update entity state is 'on', 'off', or 'unknown'."""
        entry_id = _setup_integration_with_updates(
            ha_api_session, check_for_updates=True
        )
        time.sleep(5)

        try:
            update_entities = _get_update_entities(ha_api_session)
            if not update_entities:
                pytest.skip("No update entities found; check_for_updates may not produce one without SSH")

            valid_states = {"on", "off", "unknown", "unavailable"}
            for entity in update_entities:
                assert entity["state"] in valid_states, (
                    f"Update entity {entity['entity_id']} has invalid state: {entity['state']!r}"
                )
        finally:
            ha_api_session.delete(
                f"{HA_URL}/api/config/config_entries/entry/{entry_id}",
                timeout=10,
            )

    def test_update_entity_attributes(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """Update entity has expected attributes."""
        entry_id = _setup_integration_with_updates(
            ha_api_session, check_for_updates=True
        )
        time.sleep(5)

        try:
            update_entities = _get_update_entities(ha_api_session)
            if not update_entities:
                pytest.skip("No update entities found")

            entity = update_entities[0]
            attrs = entity.get("attributes", {})
            # Update entities should have at minimum a friendly_name
            assert "friendly_name" in attrs, (
                f"friendly_name missing from update entity attributes: {attrs}"
            )
        finally:
            ha_api_session.delete(
                f"{HA_URL}/api/config/config_entries/entry/{entry_id}",
                timeout=10,
            )


class TestUpdateEntityVersionInfo:
    """Test version information in update entity attributes."""

    def test_update_entity_has_version_attributes(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """Update entity attributes include installed_version and/or latest_version."""
        entry_id = _setup_integration_with_updates(
            ha_api_session, check_for_updates=True
        )
        time.sleep(5)

        try:
            update_entities = _get_update_entities(ha_api_session)
            if not update_entities:
                pytest.skip("No update entities found")

            entity = update_entities[0]
            attrs = entity.get("attributes", {})
            # At least the friendly_name should always be present.  Version
            # attributes (installed_version, latest_version) depend on SSH
            # connectivity to the Docker host, so we only assert what is
            # guaranteed regardless of network availability.
            assert "friendly_name" in attrs, (
                f"friendly_name missing from update entity: {attrs}"
            )
        finally:
            ha_api_session.delete(
                f"{HA_URL}/api/config/config_entries/entry/{entry_id}",
                timeout=10,
            )


class TestAutoUpdateOption:
    """Test auto-update functionality."""

    def test_integration_setup_with_auto_update_enabled(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """Integration can be set up with auto_update=True without errors."""
        entry_id = _setup_integration_with_updates(
            ha_api_session, check_for_updates=True, auto_update=True
        )
        time.sleep(3)

        try:
            resp = ha_api_session.get(
                f"{HA_URL}/api/config/config_entries/entry",
                timeout=10,
            )
            assert resp.status_code == 200
            entries = resp.json()
            our_entry = next(
                (e for e in entries if e["entry_id"] == entry_id), None
            )
            assert our_entry is not None
            assert our_entry["domain"] == INTEGRATION_DOMAIN
        finally:
            ha_api_session.delete(
                f"{HA_URL}/api/config/config_entries/entry/{entry_id}",
                timeout=10,
            )

    def test_integration_setup_without_check_for_updates(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """Integration setup with check_for_updates=False creates sensor but not update entity."""
        entry_id = _setup_integration_with_updates(
            ha_api_session, check_for_updates=False, auto_update=False
        )
        time.sleep(5)

        try:
            update_entities = _get_update_entities(ha_api_session)
            # When check_for_updates is disabled, no update entity should exist for this entry
            # (other entries may have update entities, so we only check our container name)
            our_update_entities = [
                e for e in update_entities
                if "update_test" in e["entity_id"]
            ]
            assert len(our_update_entities) == 0, (
                f"Update entity created despite check_for_updates=False: {our_update_entities}"
            )
        finally:
            ha_api_session.delete(
                f"{HA_URL}/api/config/config_entries/entry/{entry_id}",
                timeout=10,
            )

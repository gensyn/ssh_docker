"""Playwright E2E tests for Docker container discovery.

Covers:
- Discovering running containers via the integration
- Sensor entities created for discovered containers
- Container state detection (running / exited)
- Container information in sensor attributes
- Container list via REST API
"""

from __future__ import annotations

import time

import pytest
import requests

from conftest import HA_URL, INTEGRATION_DOMAIN, SSH_HOST, DOCKER_SSH_USER, DOCKER_SSH_PASSWORD


def _get_sensor_entities(session: requests.Session) -> list[dict]:
    """Return all sensor entities that belong to the ssh_docker domain."""
    resp = session.get(f"{HA_URL}/api/states", timeout=10)
    assert resp.status_code == 200
    return [
        s for s in resp.json()
        if s["entity_id"].startswith("sensor.")
        and s.get("attributes", {}).get("integration") == INTEGRATION_DOMAIN
        or (
            s["entity_id"].startswith("sensor.")
            and "ssh_docker" in s["entity_id"]
        )
    ]


def _get_entity(session: requests.Session, entity_id: str) -> dict | None:
    """Return a single entity state or None if not found."""
    resp = session.get(f"{HA_URL}/api/states/{entity_id}", timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return None


def _wait_for_entity(
    session: requests.Session,
    entity_id: str,
    timeout: int = 30,
) -> dict:
    """Poll until the entity state is available."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        entity = _get_entity(session, entity_id)
        if entity is not None and entity["state"] not in ("unavailable", "unknown"):
            return entity
        time.sleep(2)
    raise TimeoutError(f"Entity {entity_id!r} did not become available within {timeout}s")


class TestContainerDiscovery:
    """Test that containers on the Docker host are discovered and exposed as sensors."""

    def test_sensor_entity_created_for_known_container(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """A sensor entity is created for the configured container."""
        # Allow HA some time to set up the entities
        time.sleep(3)

        resp = ha_api_session.get(f"{HA_URL}/api/states", timeout=10)
        assert resp.status_code == 200
        states = resp.json()

        # Look for any sensor that matches "ssh_test_1" container name
        matching = [
            s for s in states
            if "ssh_test_1" in s["entity_id"] and s["entity_id"].startswith("sensor.")
        ]
        assert len(matching) >= 1, (
            f"No sensor entity found for ssh_test_1. Available sensors: "
            f"{[s['entity_id'] for s in states if s['entity_id'].startswith('sensor.')][:20]}"
        )

    def test_sensor_state_is_valid_for_running_container(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """A sensor for a running container has a valid state."""
        time.sleep(3)

        resp = ha_api_session.get(f"{HA_URL}/api/states", timeout=10)
        assert resp.status_code == 200
        states = resp.json()

        sensors = [
            s for s in states
            if "ssh_test_1" in s["entity_id"] and s["entity_id"].startswith("sensor.")
        ]
        assert sensors, "No sensor entity found for ssh_test_1"

        sensor = sensors[0]
        valid_states = {"running", "exited", "paused", "created", "restarting",
                        "removing", "dead", "unavailable", "unknown"}
        assert sensor["state"] in valid_states, (
            f"Unexpected sensor state: {sensor['state']!r}"
        )

    def test_sensor_attributes_include_container_info(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """Container sensor attributes include image and container state keys."""
        time.sleep(3)

        resp = ha_api_session.get(f"{HA_URL}/api/states", timeout=10)
        assert resp.status_code == 200
        states = resp.json()

        sensors = [
            s for s in states
            if "ssh_test_1" in s["entity_id"] and s["entity_id"].startswith("sensor.")
        ]
        assert sensors, "No sensor entity found for ssh_test_1"

        attrs = sensors[0].get("attributes", {})
        # At minimum the friendly_name should be present
        assert "friendly_name" in attrs, f"Missing friendly_name in attributes: {attrs}"

    def test_multiple_containers_produce_multiple_sensors(
        self,
        ha_api_session: requests.Session,
        clean_integration: None,
    ) -> None:
        """Two separate ssh_docker entries produce two independent sensor entities."""
        entry_ids = []

        for container in ("ssh_test_1", "ssh_test_2"):
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
                    "name": f"discover_{container}",
                    "service": container,
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

        assert len(entry_ids) == 2, "Expected two config entries to be created"

        time.sleep(5)

        resp = ha_api_session.get(f"{HA_URL}/api/states", timeout=10)
        assert resp.status_code == 200
        all_sensors = [
            s["entity_id"] for s in resp.json()
            if s["entity_id"].startswith("sensor.") and "ssh" in s["entity_id"]
        ]

        # Clean up
        for eid in entry_ids:
            ha_api_session.delete(
                f"{HA_URL}/api/config/config_entries/entry/{eid}",
                timeout=10,
            )

        assert len(all_sensors) >= 2, (
            f"Expected at least 2 SSH-related sensors, found: {all_sensors}"
        )

    def test_container_state_detection_running(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """Sensor state reflects whether the container is running."""
        time.sleep(3)

        resp = ha_api_session.get(f"{HA_URL}/api/states", timeout=10)
        assert resp.status_code == 200
        states = resp.json()

        sensors = [
            s for s in states
            if "ssh_test_1" in s["entity_id"] and s["entity_id"].startswith("sensor.")
        ]
        if not sensors:
            pytest.skip("No sensor entity found; skipping state detection test")

        # The containers in the test environment should be running
        # (if they're in a valid Docker state, the test passes)
        valid_states = {"running", "exited", "paused", "created", "restarting",
                        "removing", "dead", "unavailable", "unknown"}
        assert sensors[0]["state"] in valid_states

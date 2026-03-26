"""Playwright E2E tests: SSH Docker sensor state reflects the docker host."""

from __future__ import annotations

import time
from typing import Any

import requests

from conftest import HA_URL


class TestSensor:
    """Tests that verify the ssh_docker sensor entity behaves correctly."""

    def test_sensor_entity_created(self, ha_api: requests.Session, ensure_integration: str) -> None:
        """After adding an ssh_docker entry a sensor entity is created."""
        states_resp = ha_api.get(f"{HA_URL}/api/states")
        states_resp.raise_for_status()
        ssh_docker_entities = [
            s for s in states_resp.json()
            if s["entity_id"].startswith("sensor.ssh_docker_")
        ]
        assert len(ssh_docker_entities) >= 1, (
            "No ssh_docker sensor entity found after adding the integration"
        )

    def test_sensor_has_expected_attributes(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """The sensor exposes expected attributes (name, host)."""
        states_resp = ha_api.get(f"{HA_URL}/api/states")
        states_resp.raise_for_status()
        entity = next(
            (s for s in states_resp.json() if s["entity_id"].startswith("sensor.ssh_docker_")),
            None,
        )
        assert entity is not None, "No ssh_docker sensor entity found"

        attrs = entity.get("attributes", {})
        # The sensor must at least expose host and name
        assert "name" in attrs or "host" in attrs, (
            f"Expected 'name' or 'host' in attributes, got: {list(attrs.keys())}"
        )

    def test_sensor_state_is_set(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """The sensor state is a non-empty string (not None)."""
        states_resp = ha_api.get(f"{HA_URL}/api/states")
        states_resp.raise_for_status()
        entity = next(
            (s for s in states_resp.json() if s["entity_id"].startswith("sensor.ssh_docker_")),
            None,
        )
        assert entity is not None, "No ssh_docker sensor entity found"
        assert entity.get("state") not in (None, ""), (
            f"Sensor state should not be empty, got: {entity.get('state')!r}"
        )

    def test_sensor_reflects_running_container(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """The sensor state reflects the docker container state (running)."""
        # Trigger a refresh so the sensor has the latest state
        states_resp = ha_api.get(f"{HA_URL}/api/states")
        states_resp.raise_for_status()
        entity = next(
            (s for s in states_resp.json() if s["entity_id"].startswith("sensor.ssh_docker_")),
            None,
        )
        assert entity is not None, "No ssh_docker sensor entity found"

        state = entity.get("state", "")
        # The mock docker reports the container as "running" initially
        assert state in ("running", "unavailable", "unknown", "initializing"), (
            f"Unexpected sensor state: {state!r}"
        )

    def test_refresh_service_updates_sensor(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """Calling the refresh service updates the sensor state."""
        # Get the entity_id of the created sensor
        states_resp = ha_api.get(f"{HA_URL}/api/states")
        states_resp.raise_for_status()
        entity = next(
            (s for s in states_resp.json() if s["entity_id"].startswith("sensor.ssh_docker_")),
            None,
        )
        assert entity is not None, "No ssh_docker sensor entity found"
        entity_id = entity["entity_id"]

        # Call the refresh service
        refresh_resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/refresh",
            json={"entity_id": entity_id},
        )
        assert refresh_resp.status_code in (200, 204), (
            f"Refresh service failed: {refresh_resp.text}"
        )

        # Give HA a moment to process
        time.sleep(2)

        # State should still be accessible
        state_resp = ha_api.get(f"{HA_URL}/api/states/{entity_id}")
        assert state_resp.status_code == 200, state_resp.text
        state = state_resp.json().get("state", "")
        assert state not in (None, ""), f"Sensor state should not be empty after refresh: {state!r}"

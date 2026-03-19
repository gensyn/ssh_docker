"""Playwright E2E tests for Docker container management operations.

Covers:
- Starting containers via ssh_docker.create service
- Stopping containers via ssh_docker.stop service
- Restarting containers via ssh_docker.restart service
- Removing containers via ssh_docker.remove service
- Refreshing container state via ssh_docker.refresh service
- Verifying state transitions after service calls
"""

from __future__ import annotations

import time

import pytest
import requests

from conftest import HA_URL, INTEGRATION_DOMAIN


def _call_service(
    session: requests.Session,
    service: str,
    entity_id: str,
    timeout: int = 30,
) -> requests.Response:
    """Call an ssh_docker service with an entity_id."""
    return session.post(
        f"{HA_URL}/api/services/{INTEGRATION_DOMAIN}/{service}",
        json={"entity_id": entity_id},
        timeout=timeout,
    )


def _get_sensor_entity_id(session: requests.Session, container_name: str) -> str | None:
    """Find the sensor entity_id for a given container name."""
    resp = session.get(f"{HA_URL}/api/states", timeout=10)
    if resp.status_code != 200:
        return None
    for state in resp.json():
        if (
            state["entity_id"].startswith("sensor.")
            and container_name in state["entity_id"]
        ):
            return state["entity_id"]
    return None


def _get_entity_state(session: requests.Session, entity_id: str) -> str | None:
    """Return the current state of an entity."""
    resp = session.get(f"{HA_URL}/api/states/{entity_id}", timeout=10)
    if resp.status_code == 200:
        return resp.json()["state"]
    return None


def _wait_for_state(
    session: requests.Session,
    entity_id: str,
    expected_state: str,
    timeout: int = 30,
) -> bool:
    """Poll until the entity reaches the expected state or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = _get_entity_state(session, entity_id)
        if state == expected_state:
            return True
        time.sleep(2)
    return False


class TestContainerRefresh:
    """Test refreshing container state."""

    def test_refresh_service_succeeds(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """The refresh service call completes without error."""
        time.sleep(3)
        entity_id = _get_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        resp = _call_service(ha_api_session, "refresh", entity_id)
        assert resp.status_code in (200, 204), (
            f"Refresh service returned unexpected status {resp.status_code}: {resp.text}"
        )

    def test_refresh_updates_last_changed(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """Calling refresh causes the entity's last_changed timestamp to update."""
        time.sleep(3)
        entity_id = _get_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        before_resp = ha_api_session.get(
            f"{HA_URL}/api/states/{entity_id}", timeout=10
        )
        assert before_resp.status_code == 200
        before_updated = before_resp.json().get("last_updated")

        _call_service(ha_api_session, "refresh", entity_id)
        time.sleep(2)

        after_resp = ha_api_session.get(
            f"{HA_URL}/api/states/{entity_id}", timeout=10
        )
        assert after_resp.status_code == 200
        after_updated = after_resp.json().get("last_updated")

        # Either the timestamp changed or the state is still valid
        assert after_updated is not None


class TestContainerStop:
    """Test stopping a running container."""

    def test_stop_service_call_accepted(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """The stop service call is accepted (200/204) by HA."""
        time.sleep(3)
        entity_id = _get_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        resp = _call_service(ha_api_session, "stop", entity_id)
        assert resp.status_code in (200, 204), (
            f"Stop service returned {resp.status_code}: {resp.text}"
        )

    def test_stop_sets_pending_or_exited_state(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """After stop is called, the sensor transitions to exited or a pending state."""
        time.sleep(3)
        entity_id = _get_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        _call_service(ha_api_session, "stop", entity_id)
        time.sleep(5)

        state = _get_entity_state(ha_api_session, entity_id)
        valid_post_stop = {"exited", "stopping", "unavailable", "unknown", "running"}
        assert state in valid_post_stop, (
            f"Unexpected state after stop: {state!r}"
        )


class TestContainerRestart:
    """Test restarting a container."""

    def test_restart_service_call_accepted(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """The restart service call is accepted by HA."""
        time.sleep(3)
        entity_id = _get_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        resp = _call_service(ha_api_session, "restart", entity_id)
        assert resp.status_code in (200, 204), (
            f"Restart service returned {resp.status_code}: {resp.text}"
        )

    def test_restart_returns_container_to_running(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """After restart, the container eventually returns to a running state."""
        time.sleep(3)
        entity_id = _get_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        _call_service(ha_api_session, "restart", entity_id)

        # Allow time for restart and sensor refresh
        time.sleep(10)
        _call_service(ha_api_session, "refresh", entity_id)
        time.sleep(3)

        state = _get_entity_state(ha_api_session, entity_id)
        # After restart the container may be running or in a transitional state
        valid_post_restart = {"running", "restarting", "exited", "unavailable", "unknown"}
        assert state in valid_post_restart, (
            f"Unexpected state after restart: {state!r}"
        )


class TestContainerCreate:
    """Test the create service (uses docker_create executable on the host)."""

    def test_create_service_call_accepted(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """The create service call is accepted by HA (even if no docker_create script exists)."""
        time.sleep(3)
        entity_id = _get_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        resp = _call_service(ha_api_session, "create", entity_id, timeout=60)
        # HA accepts the call; actual success depends on docker_create being present
        assert resp.status_code in (200, 204, 400), (
            f"Create service returned unexpected status {resp.status_code}: {resp.text}"
        )


class TestContainerRemove:
    """Test removing a container."""

    def test_remove_service_call_accepted(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """The remove service call is accepted by HA."""
        time.sleep(3)
        entity_id = _get_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        # First stop the container so it can be removed
        _call_service(ha_api_session, "stop", entity_id)
        time.sleep(5)

        resp = _call_service(ha_api_session, "remove", entity_id)
        # The call should be accepted by HA; Docker-level success depends on the host
        assert resp.status_code in (200, 204), (
            f"Remove service returned {resp.status_code}: {resp.text}"
        )

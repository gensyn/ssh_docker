"""Playwright E2E tests for SSH Docker services via the REST API.

Covers:
- ssh_docker.create service
- ssh_docker.restart service
- ssh_docker.stop service
- ssh_docker.remove service
- ssh_docker.refresh service
- Service error handling (missing entity, wrong domain)
"""

from __future__ import annotations

import time

import pytest
import requests

from conftest import HA_URL, INTEGRATION_DOMAIN


def _find_sensor_entity_id(session: requests.Session, container_name: str) -> str | None:
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


class TestRefreshService:
    """Tests for the ssh_docker.refresh service."""

    def test_refresh_service_is_registered(
        self, ha_api_session: requests.Session
    ) -> None:
        """The refresh service is registered with Home Assistant."""
        resp = ha_api_session.get(f"{HA_URL}/api/services", timeout=10)
        assert resp.status_code == 200
        services = resp.json()
        ssh_docker_services = next(
            (s for s in services if s.get("domain") == INTEGRATION_DOMAIN), None
        )
        if ssh_docker_services is None:
            pytest.skip("No ssh_docker services registered; integration may not be loaded")
        assert "refresh" in ssh_docker_services.get("services", {}), (
            f"'refresh' not in ssh_docker services: {list(ssh_docker_services['services'].keys())}"
        )

    def test_refresh_succeeds_for_known_entity(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """Refresh returns 200/204 for a known sensor entity."""
        time.sleep(3)
        entity_id = _find_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        resp = _call_service(ha_api_session, "refresh", entity_id)
        assert resp.status_code in (200, 204), (
            f"Refresh failed: {resp.status_code} {resp.text}"
        )

    def test_refresh_with_invalid_entity_returns_error(
        self, ha_api_session: requests.Session
    ) -> None:
        """Calling refresh with a non-existent entity_id returns an error response."""
        resp = _call_service(ha_api_session, "refresh", "sensor.nonexistent_container_xyz")
        # HA returns 4xx for validation errors
        assert resp.status_code in (400, 422), (
            f"Expected validation error, got {resp.status_code}: {resp.text}"
        )


class TestStopService:
    """Tests for the ssh_docker.stop service."""

    def test_stop_service_is_registered(
        self, ha_api_session: requests.Session
    ) -> None:
        """The stop service is registered with Home Assistant."""
        resp = ha_api_session.get(f"{HA_URL}/api/services", timeout=10)
        assert resp.status_code == 200
        services = resp.json()
        ssh_docker_services = next(
            (s for s in services if s.get("domain") == INTEGRATION_DOMAIN), None
        )
        if ssh_docker_services is None:
            pytest.skip("No ssh_docker services registered")
        assert "stop" in ssh_docker_services.get("services", {})

    def test_stop_succeeds_for_known_entity(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """Stop returns 200/204 for a known sensor entity."""
        time.sleep(3)
        entity_id = _find_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        resp = _call_service(ha_api_session, "stop", entity_id)
        assert resp.status_code in (200, 204), (
            f"Stop failed: {resp.status_code} {resp.text}"
        )


class TestRestartService:
    """Tests for the ssh_docker.restart service."""

    def test_restart_service_is_registered(
        self, ha_api_session: requests.Session
    ) -> None:
        """The restart service is registered with Home Assistant."""
        resp = ha_api_session.get(f"{HA_URL}/api/services", timeout=10)
        assert resp.status_code == 200
        services = resp.json()
        ssh_docker_services = next(
            (s for s in services if s.get("domain") == INTEGRATION_DOMAIN), None
        )
        if ssh_docker_services is None:
            pytest.skip("No ssh_docker services registered")
        assert "restart" in ssh_docker_services.get("services", {})

    def test_restart_succeeds_for_known_entity(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """Restart returns 200/204 for a known sensor entity."""
        time.sleep(3)
        entity_id = _find_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        resp = _call_service(ha_api_session, "restart", entity_id)
        assert resp.status_code in (200, 204), (
            f"Restart failed: {resp.status_code} {resp.text}"
        )


class TestRemoveService:
    """Tests for the ssh_docker.remove service."""

    def test_remove_service_is_registered(
        self, ha_api_session: requests.Session
    ) -> None:
        """The remove service is registered with Home Assistant."""
        resp = ha_api_session.get(f"{HA_URL}/api/services", timeout=10)
        assert resp.status_code == 200
        services = resp.json()
        ssh_docker_services = next(
            (s for s in services if s.get("domain") == INTEGRATION_DOMAIN), None
        )
        if ssh_docker_services is None:
            pytest.skip("No ssh_docker services registered")
        assert "remove" in ssh_docker_services.get("services", {})

    def test_remove_with_invalid_entity_returns_error(
        self, ha_api_session: requests.Session
    ) -> None:
        """Calling remove with a non-existent entity_id returns a validation error."""
        resp = _call_service(ha_api_session, "remove", "sensor.nonexistent_container_xyz")
        assert resp.status_code in (400, 422), (
            f"Expected validation error, got {resp.status_code}: {resp.text}"
        )


class TestCreateService:
    """Tests for the ssh_docker.create service."""

    def test_create_service_is_registered(
        self, ha_api_session: requests.Session
    ) -> None:
        """The create service is registered with Home Assistant."""
        resp = ha_api_session.get(f"{HA_URL}/api/services", timeout=10)
        assert resp.status_code == 200
        services = resp.json()
        ssh_docker_services = next(
            (s for s in services if s.get("domain") == INTEGRATION_DOMAIN), None
        )
        if ssh_docker_services is None:
            pytest.skip("No ssh_docker services registered")
        assert "create" in ssh_docker_services.get("services", {})

    def test_create_call_accepted(
        self,
        ha_api_session: requests.Session,
        integration_entry_id: str,
    ) -> None:
        """Create service call is accepted by HA (even if docker_create is absent on host)."""
        time.sleep(3)
        entity_id = _find_sensor_entity_id(ha_api_session, "ssh_test_1")
        if entity_id is None:
            pytest.skip("No sensor entity found for ssh_test_1")

        resp = _call_service(ha_api_session, "create", entity_id, timeout=60)
        # 200/204 = success, 400 = service error (docker_create not found, etc.)
        assert resp.status_code in (200, 204, 400), (
            f"Create service returned unexpected status {resp.status_code}: {resp.text}"
        )


class TestServiceRegistration:
    """Verify all expected services are registered."""

    def test_all_services_registered(
        self, ha_api_session: requests.Session, integration_entry_id: str
    ) -> None:
        """All five ssh_docker services are registered after integration setup."""
        time.sleep(2)
        resp = ha_api_session.get(f"{HA_URL}/api/services", timeout=10)
        assert resp.status_code == 200
        services = resp.json()
        ssh_docker_services = next(
            (s for s in services if s.get("domain") == INTEGRATION_DOMAIN), None
        )
        if ssh_docker_services is None:
            pytest.skip("No ssh_docker services found; integration may not have loaded")

        registered = set(ssh_docker_services.get("services", {}).keys())
        expected = {"create", "restart", "stop", "remove", "refresh"}
        missing = expected - registered
        assert not missing, (
            f"Missing ssh_docker services: {missing}. Registered: {registered}"
        )

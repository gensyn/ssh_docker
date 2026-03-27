"""Playwright E2E tests: ssh_docker service interface."""

from __future__ import annotations

import time
from typing import Any

import requests

from conftest import HA_URL


def _get_ssh_docker_entity(ha_api: requests.Session) -> dict | None:
    """Return the first ssh_docker sensor entity, or None if not found."""
    resp = ha_api.get(f"{HA_URL}/api/states")
    resp.raise_for_status()
    return next(
        (s for s in resp.json() if s["entity_id"].startswith("sensor.ssh_docker_")),
        None,
    )


class TestServices:
    """Tests focused on the HA service interface of SSH Docker."""

    def test_services_registered(self, ha_api: requests.Session, ensure_integration: str) -> None:
        """All ssh_docker services should appear in the HA services list."""
        resp = ha_api.get(f"{HA_URL}/api/services")
        resp.raise_for_status()
        services = resp.json()
        ssh_docker_domain = next(
            (svc for svc in services if svc["domain"] == "ssh_docker"), None
        )
        assert ssh_docker_domain is not None, "ssh_docker domain not found in services list"

        registered = set(ssh_docker_domain.get("services", {}).keys())
        expected = {"restart", "stop", "remove", "refresh", "get_logs", "execute_command"}
        assert expected.issubset(registered), (
            f"Missing services: {expected - registered}.  Registered: {registered}"
        )

    def test_refresh_service_succeeds(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """The refresh service completes without error."""
        entity = _get_ssh_docker_entity(ha_api)
        assert entity is not None, "No ssh_docker sensor entity found"

        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/refresh",
            json={"entity_id": entity["entity_id"]},
        )
        assert resp.status_code in (200, 204), f"refresh service failed: {resp.text}"

    def test_get_logs_returns_content(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """The get_logs service returns a non-empty logs string."""
        entity = _get_ssh_docker_entity(ha_api)
        assert entity is not None, "No ssh_docker sensor entity found"

        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/get_logs?return_response",
            json={"entity_id": entity["entity_id"]},
        )
        assert resp.status_code == 200, f"get_logs service failed: {resp.text}"
        data = resp.json()
        # HA wraps service responses in {"service_response": {...}}
        service_response = data.get("service_response", data)
        assert "logs" in service_response, (
            f"Expected 'logs' key in service response, got: {list(service_response.keys())}"
        )

    def test_stop_and_restart_service(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """Stop followed by restart transitions the sensor state correctly.

        HA's REST service API returns 200 immediately after *queuing* the
        service, before the coordinator's SSH stop + inspect cycle completes.
        We therefore poll the entity state with a generous timeout instead of
        using a fixed sleep.
        """
        entity = _get_ssh_docker_entity(ha_api)
        assert entity is not None, "No ssh_docker sensor entity found"
        entity_id = entity["entity_id"]

        def wait_for_state(expected_states: tuple, timeout: int = 45) -> str:
            """Poll the entity state until it is one of *expected_states* or timeout."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                resp = ha_api.get(f"{HA_URL}/api/states/{entity_id}")
                if resp.status_code == 200:
                    state = resp.json().get("state", "")
                    if state in expected_states:
                        return state
                time.sleep(2)
            # Return whatever state we have at timeout
            resp = ha_api.get(f"{HA_URL}/api/states/{entity_id}")
            return resp.json().get("state", "") if resp.status_code == 200 else ""

        # Stop the container
        stop_resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/stop",
            json={"entity_id": entity_id},
        )
        assert stop_resp.status_code in (200, 204), f"stop service failed: {stop_resp.text}"

        # Wait for the coordinator to finish the SSH stop → inspect cycle
        stopped_state = wait_for_state(("exited", "unavailable", "unknown"))
        assert stopped_state in ("exited", "unavailable", "unknown"), (
            f"Expected exited/unavailable after stop, got: {stopped_state!r}"
        )

        # Restart the container
        restart_resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/restart",
            json={"entity_id": entity_id},
        )
        assert restart_resp.status_code in (200, 204), (
            f"restart service failed: {restart_resp.text}"
        )

        # Wait for the coordinator to finish the SSH restart → inspect cycle
        running_state = wait_for_state(("running", "unavailable", "unknown"))
        assert running_state in ("running", "unavailable", "unknown"), (
            f"Expected running/unavailable after restart, got: {running_state!r}"
        )

    def test_service_requires_entity_id(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """Calling a service without entity_id returns a 422 validation error."""
        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/refresh",
            json={},  # missing entity_id
        )
        assert resp.status_code in (400, 422), (
            f"Expected validation error (400/422) for missing entity_id, got {resp.status_code}"
        )

    def test_service_with_invalid_entity_id(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """Calling a service with a non-existent entity_id returns an error."""
        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/refresh",
            json={"entity_id": "sensor.nonexistent_entity_xyz"},
        )
        assert resp.status_code >= 400, (
            f"Expected error for invalid entity_id, got {resp.status_code}"
        )

    def test_api_requires_authentication(self) -> None:
        """Calling a service API without an auth token returns 401."""
        resp = requests.post(
            f"{HA_URL}/api/services/ssh_docker/refresh",
            json={"entity_id": "sensor.ssh_docker_test_app"},
            timeout=10,
        )
        assert resp.status_code == 401, resp.text


class TestExecuteCommand:
    """Tests focused on the execute_command service."""

    def test_execute_command_returns_output_and_exit_status(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """execute_command runs a command and returns output + exit_status."""
        entity = _get_ssh_docker_entity(ha_api)
        assert entity is not None, "No ssh_docker sensor entity found"

        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/execute_command?return_response",
            json={"entity_id": entity["entity_id"], "command": "echo hello"},
        )
        assert resp.status_code == 200, f"execute_command service failed: {resp.text}"
        data = resp.json()
        service_response = data.get("service_response", data)
        assert "output" in service_response, (
            f"Expected 'output' key in response, got: {list(service_response.keys())}"
        )
        assert "exit_status" in service_response, (
            f"Expected 'exit_status' key in response, got: {list(service_response.keys())}"
        )
        assert "hello" in service_response["output"], (
            f"Expected 'hello' in output, got: {service_response['output']!r}"
        )
        assert service_response["exit_status"] == 0, (
            f"Expected exit_status 0, got: {service_response['exit_status']}"
        )

    def test_execute_command_captures_nonzero_exit_status(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """execute_command captures non-zero exit codes from failing commands."""
        entity = _get_ssh_docker_entity(ha_api)
        assert entity is not None, "No ssh_docker sensor entity found"

        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/execute_command?return_response",
            json={"entity_id": entity["entity_id"], "command": "exit 42"},
        )
        assert resp.status_code == 200, f"execute_command service failed: {resp.text}"
        data = resp.json()
        service_response = data.get("service_response", data)
        assert service_response.get("exit_status") == 42, (
            f"Expected exit_status 42, got: {service_response.get('exit_status')}"
        )

    def test_execute_command_with_explicit_timeout(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """execute_command accepts an explicit timeout parameter."""
        entity = _get_ssh_docker_entity(ha_api)
        assert entity is not None, "No ssh_docker sensor entity found"

        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/execute_command?return_response",
            json={
                "entity_id": entity["entity_id"],
                "command": "echo success",
                "timeout": 30,
            },
        )
        assert resp.status_code == 200, f"execute_command with timeout failed: {resp.text}"
        data = resp.json()
        service_response = data.get("service_response", data)
        assert service_response.get("exit_status") == 0, (
            f"Expected exit_status 0, got: {service_response.get('exit_status')}"
        )

    def test_execute_command_requires_command_field(
        self, ha_api: requests.Session, ensure_integration: str
    ) -> None:
        """Calling execute_command without the command field returns a validation error."""
        entity = _get_ssh_docker_entity(ha_api)
        assert entity is not None, "No ssh_docker sensor entity found"

        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_docker/execute_command?return_response",
            json={"entity_id": entity["entity_id"]},  # missing command
        )
        assert resp.status_code in (400, 422), (
            f"Expected validation error (400/422) for missing command, got {resp.status_code}"
        )

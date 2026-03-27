"""Integration tests for the SSH Docker custom component.

These tests use ``pytest-homeassistant-custom-component`` which spins up a
real (in-process) Home Assistant instance per test.  No hand-rolled mocks are
needed: the ``hass`` fixture IS a real ``HomeAssistant`` object, and entities,
states, and services all behave exactly as they do at runtime.

Run with:
    pytest tests/integration_tests/ -v
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ssh_docker.const import (
    CONF_AUTO_UPDATE,
    CONF_CHECK_FOR_UPDATES,
    CONF_DOCKER_COMMAND,
    CONF_SERVICE,
    DOMAIN,
    SERVICE_CREATE,
    SERVICE_EXECUTE_COMMAND,
    SERVICE_GET_LOGS,
    SERVICE_REFRESH,
    SERVICE_REMOVE,
    SERVICE_RESTART,
    SERVICE_STOP,
)
from custom_components.ssh_docker.coordinator import SshDockerCoordinator

from .conftest import _default_ssh_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id="entry1",
    name="my_container",
    service=None,
    host="192.168.1.100",
    username="user",
    password="pass",
    docker_command="docker",
    check_known_hosts=True,
    auto_update=False,
    check_for_updates=False,
):
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title=name,
        data={
            "name": name,
            CONF_SERVICE: service if service is not None else name,
        },
        options={
            "host": host,
            "username": username,
            "password": password,
            CONF_DOCKER_COMMAND: docker_command,
            "check_known_hosts": check_known_hosts,
            CONF_AUTO_UPDATE: auto_update,
            CONF_CHECK_FOR_UPDATES: check_for_updates,
        },
        version=1,
    )


async def _setup_entry(hass, entry):
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# Entry setup
# ---------------------------------------------------------------------------


class TestSetupEntry:
    """Config entry setup creates the expected entities and coordinator."""

    async def test_sensor_entity_created(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.states.get("sensor.ssh_docker_my_container") is not None

    async def test_update_entity_created(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.states.get("update.ssh_docker_my_container") is not None

    async def test_coordinator_stored_in_hass_data(self, hass, mock_ssh):
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)
        coordinator = hass.data[DOMAIN]["e1"]
        assert isinstance(coordinator, SshDockerCoordinator)

    async def test_setup_returns_true(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert "entry1" in hass.data.get(DOMAIN, {})

    async def test_sensor_state_after_first_fetch(self, hass, mock_ssh):
        """After the first update the sensor reflects docker inspect output."""
        entry = _make_entry()
        await _setup_entry(hass, entry)
        state = hass.states.get("sensor.ssh_docker_my_container")
        assert state.state == "running"

    async def test_sensor_attributes_after_first_fetch(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        attrs = hass.states.get("sensor.ssh_docker_my_container").attributes
        assert attrs["image"] == "nginx:latest"
        assert attrs["created"] == "2024-01-01T00:00:00Z"
        assert attrs["update_available"] is False
        assert attrs["host"] == "192.168.1.100"
        assert attrs["docker_create_available"] is True

    async def test_sensor_host_attribute_reflects_configured_host(self, hass, mock_ssh):
        entry = _make_entry(host="10.20.30.40")
        await _setup_entry(hass, entry)
        attrs = hass.states.get("sensor.ssh_docker_my_container").attributes
        assert attrs["host"] == "10.20.30.40"


# ---------------------------------------------------------------------------
# Services registration
# ---------------------------------------------------------------------------


class TestServicesRegistered:
    """All five Docker services are registered during async_setup."""

    async def test_create_service_registered(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.services.has_service(DOMAIN, SERVICE_CREATE)

    async def test_restart_service_registered(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.services.has_service(DOMAIN, SERVICE_RESTART)

    async def test_stop_service_registered(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.services.has_service(DOMAIN, SERVICE_STOP)

    async def test_remove_service_registered(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.services.has_service(DOMAIN, SERVICE_REMOVE)

    async def test_refresh_service_registered(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.services.has_service(DOMAIN, SERVICE_REFRESH)

    async def test_get_logs_service_registered(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.services.has_service(DOMAIN, SERVICE_GET_LOGS)

    async def test_execute_command_service_registered(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.services.has_service(DOMAIN, SERVICE_EXECUTE_COMMAND)


# ---------------------------------------------------------------------------
# docker_services availability check
# ---------------------------------------------------------------------------


class TestDockerServicesCheck:
    """docker_services availability check gates entry setup."""

    async def test_setup_proceeds_when_docker_services_absent(self, hass):
        """Setup succeeds when docker_services is not on the host."""
        entry = _make_entry()

        async def mock_run(h, opts, cmd, timeout=60):
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert "entry1" in hass.data.get(DOMAIN, {})

    async def test_setup_proceeds_when_service_in_list(self, hass):
        """Setup succeeds when docker_services lists this service."""
        entry = _make_entry(name="my_container")

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:abc123456789", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:abc123456789", 0
            if "docker_create" in cmd:
                return "found", 0
            return '["my_container", "other_service"]', 0

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert "entry1" in hass.data.get(DOMAIN, {})

    async def test_setup_fails_when_service_absent_from_list(self, hass):
        """Setup returns False when docker_services omits this service."""
        entry = _make_entry(name="removed_service")

        async def mock_run(h, opts, cmd, timeout=60):
            return '["other_service", "another_service"]', 0

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert "entry1" not in hass.data.get(DOMAIN, {})

    async def test_setup_proceeds_when_ssh_raises(self, hass):
        """Setup proceeds when the SSH call for docker_services raises."""
        entry = _make_entry()

        async def mock_run(h, opts, cmd, timeout=60):
            raise OSError("Connection refused")

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            entry.add_to_hass(hass)
            result = await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert result is True


# ---------------------------------------------------------------------------
# docker_services caching
# ---------------------------------------------------------------------------


class TestDockerServicesCaching:
    """docker_services result is cached per host for the scan interval TTL."""

    async def test_same_host_second_entry_reuses_cache(self, hass):
        """Two entries on the same host share one cached availability check."""
        entry_a = _make_entry(entry_id="ea", name="svc_a", host="10.0.0.1")
        entry_b = _make_entry(entry_id="eb", name="svc_b", host="10.0.0.1")
        call_count = 0

        async def mock_run(h, opts, cmd, timeout=60):
            nonlocal call_count
            # Count only docker_services *availability* checks (not discover_services
            # which also contains "docker ps -a" in its else-branch).
            if "docker_services" in cmd and "docker ps" not in cmd:
                call_count += 1
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry_a)
            await _setup_entry(hass, entry_b)

        assert call_count == 1

    async def test_different_hosts_each_trigger_ssh(self, hass):
        """Two entries on different hosts each incur their own availability check."""
        entry_a = _make_entry(entry_id="ea", name="svc", host="10.0.0.1")
        entry_b = _make_entry(entry_id="eb", name="svc", host="10.0.0.2")
        call_count = 0

        async def mock_run(h, opts, cmd, timeout=60):
            nonlocal call_count
            # Count only docker_services availability checks.
            if "docker_services" in cmd and "docker ps" not in cmd:
                call_count += 1
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry_a)
            await _setup_entry(hass, entry_b)

        assert call_count == 2

    async def test_cache_stores_none_when_services_absent(self, hass):
        """When docker_services is absent, None is cached."""
        import custom_components.ssh_docker.coordinator as coord
        entry = _make_entry(entry_id="e1", host="10.0.0.5")

        async def mock_run(h, opts, cmd, timeout=60):
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            entry.add_to_hass(hass)
            await hass.config_entries.async_setup(entry.entry_id)

        cached = coord._DOCKER_SERVICES_CACHE.get("10.0.0.5")
        assert cached is not None
        assert cached[0] is None

    async def test_cache_expires_after_ttl(self, hass):
        """An expired cache entry triggers a fresh availability check."""
        import custom_components.ssh_docker.coordinator as coord
        entry = _make_entry(entry_id="e1", host="10.0.0.6")
        call_count = 0

        async def mock_run(h, opts, cmd, timeout=60):
            nonlocal call_count
            if "docker_services" in cmd and "docker ps" not in cmd:
                call_count += 1
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        first_count = call_count

        host = "10.0.0.6"
        service_names, _ = coord._DOCKER_SERVICES_CACHE[host]
        coord._DOCKER_SERVICES_CACHE[host] = (
            service_names,
            time.monotonic() - coord._DOCKER_SERVICES_CACHE_TTL - 1,
        )

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()

        assert call_count > first_count


# ---------------------------------------------------------------------------
# docker_create availability caching
# ---------------------------------------------------------------------------


class TestDockerCreateCaching:
    """docker_create availability is cached per host."""

    async def test_docker_create_cached_after_first_fetch(self, hass, mock_ssh):
        import custom_components.ssh_docker.coordinator as coord
        entry = _make_entry(host="10.0.0.10")
        await _setup_entry(hass, entry)

        cached = coord._DOCKER_CREATE_CACHE.get("10.0.0.10")
        assert cached is not None
        available, _ = cached
        assert available is True

    async def test_docker_create_not_available_cached(self, hass):
        """When docker_create is absent the cache stores False."""
        import custom_components.ssh_docker.coordinator as coord
        entry = _make_entry(host="10.0.0.11")

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:abc123456789", 0
            if "docker_create" in cmd:
                return "not_found", 0
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        cached = coord._DOCKER_CREATE_CACHE.get("10.0.0.11")
        assert cached is not None
        available, _ = cached
        assert available is False

    async def test_docker_create_cache_reused_same_host(self, hass):
        """Two entries on the same host share the docker_create availability cache."""
        entry_a = _make_entry(entry_id="ea", name="svc_a", host="10.0.0.12")
        entry_b = _make_entry(entry_id="eb", name="svc_b", host="10.0.0.12")
        check_count = 0

        async def mock_run(h, opts, cmd, timeout=60):
            nonlocal check_count
            # Count only the docker_create availability checks (contain "echo found").
            if "docker_create" in cmd and "echo found" in cmd:
                check_count += 1
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry_a)
            await _setup_entry(hass, entry_b)

        assert check_count == 1


# ---------------------------------------------------------------------------
# Sensor state and attributes
# ---------------------------------------------------------------------------


class TestSensorState:
    """DockerContainerSensor reflects docker inspect output."""

    async def test_running_container_state(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.states.get("sensor.ssh_docker_my_container").state == "running"

    async def test_exited_container_state(self, hass):
        entry = _make_entry()

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "exited;2024-01-01T00:00:00Z;nginx:latest;sha256:abc123456789", 0
            if "docker_create" in cmd:
                return "found", 0
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert hass.states.get("sensor.ssh_docker_my_container").state == "exited"

    async def test_unavailable_when_inspect_fails(self, hass):
        entry = _make_entry()

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "", 1
            if "docker_create" in cmd:
                return "not_found", 0
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert hass.states.get("sensor.ssh_docker_my_container").state == "unavailable"

    async def test_unavailable_when_ssh_raises(self, hass):
        entry = _make_entry()
        call_count = 0

        async def mock_run(h, opts, cmd, timeout=60):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "", 1  # docker_services check → absent, setup proceeds
            raise OSError("Connection refused")

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert hass.states.get("sensor.ssh_docker_my_container").state == "unavailable"

    async def test_sensor_image_attribute(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.states.get("sensor.ssh_docker_my_container").attributes["image"] == "nginx:latest"

    async def test_sensor_created_attribute(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.states.get("sensor.ssh_docker_my_container").attributes["created"] == "2024-01-01T00:00:00Z"

    async def test_sensor_docker_create_available_true(self, hass, mock_ssh):
        entry = _make_entry()
        await _setup_entry(hass, entry)
        assert hass.states.get("sensor.ssh_docker_my_container").attributes["docker_create_available"] is True

    async def test_sensor_docker_create_available_false(self, hass):
        entry = _make_entry()

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:abc123456789", 0
            if "docker_create" in cmd:
                return "not_found", 0
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert hass.states.get("sensor.ssh_docker_my_container").attributes["docker_create_available"] is False

    async def test_sensor_name_attribute(self, hass, mock_ssh):
        entry = _make_entry(name="my_container")
        await _setup_entry(hass, entry)
        assert hass.states.get("sensor.ssh_docker_my_container").attributes["name"] == "my_container"


# ---------------------------------------------------------------------------
# check_for_updates option
# ---------------------------------------------------------------------------


class TestCheckForUpdatesOption:
    """check_for_updates=True triggers a docker pull to detect newer images."""

    async def test_no_update_when_image_unchanged(self, hass):
        entry = _make_entry(check_for_updates=True)

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:abc123456789", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:abc123456789", 0
            if "docker_create" in cmd:
                return "found", 0
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert hass.states.get("sensor.ssh_docker_my_container").attributes["update_available"] is False

    async def test_update_available_when_image_changed(self, hass):
        entry = _make_entry(check_for_updates=True)

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:old111111111", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:new222222222", 0
            if "docker_create" in cmd:
                return "found", 0
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert hass.states.get("sensor.ssh_docker_my_container").attributes["update_available"] is True

    async def test_check_for_updates_false_skips_pull(self, hass):
        entry = _make_entry(check_for_updates=False)
        pull_called = []

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker pull" in cmd or "image inspect" in cmd:
                pull_called.append(cmd)
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert pull_called == []


# ---------------------------------------------------------------------------
# docker_command option
# ---------------------------------------------------------------------------


class TestDockerCommandOption:
    """docker_command option is used in all docker inspect / action commands."""

    async def test_custom_docker_command_used_in_inspect(self, hass):
        entry = _make_entry(docker_command="sudo docker")
        commands_seen = []

        async def mock_run(h, opts, cmd, timeout=60):
            commands_seen.append(cmd)
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        inspect_cmds = [c for c in commands_seen if "inspect" in c]
        assert any("sudo docker" in c for c in inspect_cmds), (
            f"Expected 'sudo docker' in inspect commands; got: {inspect_cmds}"
        )

    async def test_default_docker_command_is_docker(self, hass):
        entry = _make_entry(docker_command="docker")
        commands_seen = []

        async def mock_run(h, opts, cmd, timeout=60):
            commands_seen.append(cmd)
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        inspect_cmds = [c for c in commands_seen if "docker inspect" in c]
        assert len(inspect_cmds) > 0


# ---------------------------------------------------------------------------
# auto_update option
# ---------------------------------------------------------------------------


class TestAutoUpdateOption:
    """auto_update=True triggers automatic container recreation when update found."""

    async def test_auto_update_triggers_docker_create(self, hass):
        """When a newer image is found and auto_update=True, docker_create is run."""
        entry = _make_entry(auto_update=True, check_for_updates=True)
        create_called = []

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker_create" in cmd and "if command -v" in cmd:
                create_called.append(cmd)
                return "", 0
            if "docker inspect" in cmd and "image inspect" not in cmd:
                if not create_called:
                    return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:old111111111", 0
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:new222222222", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:new222222222", 0
            if "docker_create" in cmd:
                return "found", 0
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert len(create_called) > 0

    async def test_auto_update_disabled_does_not_recreate(self, hass):
        entry = _make_entry(auto_update=False, check_for_updates=True)
        create_called = []

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker_create" in cmd and "if command -v" in cmd:
                create_called.append(cmd)
                return "", 0
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:old111111111", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:new222222222", 0
            if "docker_create" in cmd:
                return "found", 0
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        assert create_called == []

    async def test_auto_update_sets_recreating_pending_state(self, hass):
        """auto_update calls set_pending_state('recreating') during auto-recreate.

        Patching set_pending_state at the CLASS level ensures the interception is
        in place before any background task runs, avoiding the timing race that
        would occur when replacing the method on the coordinator instance after
        setup has already started.
        """
        entry = _make_entry(auto_update=True, check_for_updates=True)
        pending_states_seen = []
        original_set_pending = SshDockerCoordinator.set_pending_state

        def capture(self_coord, state):
            pending_states_seen.append(state)
            original_set_pending(self_coord, state)

        async def update_mock(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:old111111111", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:new222222222", 0
            if "docker_create" in cmd:
                return "found", 0
            if "docker_services" in cmd:
                return "", 1
            return "", 0

        with patch.object(SshDockerCoordinator, "set_pending_state", capture), \
             patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=update_mock), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=update_mock):
            await _setup_entry(hass, entry)
            await hass.async_block_till_done()

        assert "recreating" in pending_states_seen


# ---------------------------------------------------------------------------
# Service mechanics
# ---------------------------------------------------------------------------


class TestServiceMechanics:
    """Calling services triggers coordinator actions and sets pending states."""

    async def test_restart_sets_starting_pending_state(self, hass, mock_ssh):
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["e1"]
        pending_states = []
        original = coordinator.set_pending_state

        def capture(state):
            pending_states.append(state)
            original(state)

        coordinator.set_pending_state = capture

        await hass.services.async_call(
            DOMAIN, SERVICE_RESTART,
            {"entity_id": "sensor.ssh_docker_my_container"},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert "starting" in pending_states

    async def test_stop_sets_stopping_pending_state(self, hass, mock_ssh):
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["e1"]
        pending_states = []
        original = coordinator.set_pending_state

        def capture(state):
            pending_states.append(state)
            original(state)

        coordinator.set_pending_state = capture

        await hass.services.async_call(
            DOMAIN, SERVICE_STOP,
            {"entity_id": "sensor.ssh_docker_my_container"},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert "stopping" in pending_states

    async def test_remove_sets_removing_pending_state(self, hass, mock_ssh):
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["e1"]
        pending_states = []
        original = coordinator.set_pending_state

        def capture(state):
            pending_states.append(state)
            original(state)

        coordinator.set_pending_state = capture

        await hass.services.async_call(
            DOMAIN, SERVICE_REMOVE,
            {"entity_id": "sensor.ssh_docker_my_container"},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert "removing" in pending_states

    async def test_create_sets_creating_pending_state(self, hass, mock_ssh):
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["e1"]
        pending_states = []
        original = coordinator.set_pending_state

        def capture(state):
            pending_states.append(state)
            original(state)

        coordinator.set_pending_state = capture

        await hass.services.async_call(
            DOMAIN, SERVICE_CREATE,
            {"entity_id": "sensor.ssh_docker_my_container"},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert "creating" in pending_states

    async def test_refresh_sets_refreshing_pending_state(self, hass, mock_ssh):
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["e1"]
        pending_states = []
        original = coordinator.set_pending_state

        def capture(state):
            pending_states.append(state)
            original(state)

        coordinator.set_pending_state = capture

        await hass.services.async_call(
            DOMAIN, SERVICE_REFRESH,
            {"entity_id": "sensor.ssh_docker_my_container"},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert "refreshing" in pending_states

    async def test_restart_issues_docker_restart_command(self, hass):
        entry = _make_entry(entry_id="e1")
        commands_seen = []

        async def mock_run(h, opts, cmd, timeout=60):
            commands_seen.append(cmd)
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            commands_seen.clear()
            await hass.services.async_call(
                DOMAIN, SERVICE_RESTART,
                {"entity_id": "sensor.ssh_docker_my_container"},
                blocking=True,
            )
            await hass.async_block_till_done()

        assert any("restart" in c for c in commands_seen)

    async def test_stop_issues_docker_stop_command(self, hass):
        entry = _make_entry(entry_id="e1")
        commands_seen = []

        async def mock_run(h, opts, cmd, timeout=60):
            commands_seen.append(cmd)
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            commands_seen.clear()
            await hass.services.async_call(
                DOMAIN, SERVICE_STOP,
                {"entity_id": "sensor.ssh_docker_my_container"},
                blocking=True,
            )
            await hass.async_block_till_done()

        assert any("stop" in c for c in commands_seen)

    async def test_remove_issues_docker_rm_command(self, hass):
        entry = _make_entry(entry_id="e1")
        commands_seen = []

        async def mock_run(h, opts, cmd, timeout=60):
            commands_seen.append(cmd)
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            commands_seen.clear()
            await hass.services.async_call(
                DOMAIN, SERVICE_REMOVE,
                {"entity_id": "sensor.ssh_docker_my_container"},
                blocking=True,
            )
            await hass.async_block_till_done()

        assert any("rm" in c for c in commands_seen)

    async def test_create_checks_docker_create_executable(self, hass):
        entry = _make_entry(entry_id="e1")
        check_cmds = []

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker_create" in cmd and "echo found" in cmd:
                check_cmds.append(cmd)
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            await hass.services.async_call(
                DOMAIN, SERVICE_CREATE,
                {"entity_id": "sensor.ssh_docker_my_container"},
                blocking=True,
            )
            await hass.async_block_till_done()

        assert len(check_cmds) > 0

    async def test_execute_command_returns_output_and_exit_status(self, hass):
        """execute_command issues a docker exec command and returns output + exit_status."""
        entry = _make_entry(entry_id="e1")
        commands_seen: list[str] = []

        async def mock_run(h, opts, cmd, timeout=60):
            commands_seen.append(cmd)
            if "exec" in cmd and "echo hello" in cmd:
                return "hello\n", 0
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            commands_seen.clear()
            result = await hass.services.async_call(
                DOMAIN, SERVICE_EXECUTE_COMMAND,
                {"entity_id": "sensor.ssh_docker_my_container", "command": "echo hello"},
                blocking=True,
                return_response=True,
            )
            await hass.async_block_till_done()

        assert any("exec" in c for c in commands_seen), (
            f"Expected a docker exec command, got: {commands_seen}"
        )
        assert result is not None, "Expected a service response"
        assert result.get("output") == "hello\n", f"Unexpected output: {result.get('output')!r}"
        assert result.get("exit_status") == 0, f"Unexpected exit_status: {result.get('exit_status')}"

    async def test_execute_command_forwards_timeout(self, hass):
        """execute_command forwards the timeout parameter to _ssh_run."""
        entry = _make_entry(entry_id="e1")
        captured_timeouts: list[int] = []

        async def mock_run(h, opts, cmd, timeout=60):
            if "exec" in cmd:
                captured_timeouts.append(timeout)
                return "output\n", 0
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            await hass.services.async_call(
                DOMAIN, SERVICE_EXECUTE_COMMAND,
                {"entity_id": "sensor.ssh_docker_my_container", "command": "id", "timeout": 120},
                blocking=True,
                return_response=True,
            )
            await hass.async_block_till_done()

        assert len(captured_timeouts) == 1
        assert captured_timeouts[0] == 120, (
            f"Expected timeout 120, got: {captured_timeouts[0]}"
        )

    async def test_execute_command_captures_nonzero_exit_status(self, hass):
        """execute_command returns the non-zero exit code from the remote command."""
        entry = _make_entry(entry_id="e1")

        async def mock_run(h, opts, cmd, timeout=60):
            if "exec" in cmd:
                return "error output\n", 42
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            result = await hass.services.async_call(
                DOMAIN, SERVICE_EXECUTE_COMMAND,
                {"entity_id": "sensor.ssh_docker_my_container", "command": "exit 42"},
                blocking=True,
                return_response=True,
            )
            await hass.async_block_till_done()

        assert result is not None, "Expected a service response"
        assert result.get("exit_status") == 42, (
            f"Expected exit_status 42, got: {result.get('exit_status')}"
        )


class TestUpdateEntity:
    """DockerContainerUpdateEntity reflects coordinator update state."""

    async def test_installed_version_set_after_fetch(self, hass):
        entry = _make_entry(check_for_updates=True)

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:abc123456789def0", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:abc123456789def0", 0
            if "docker_create" in cmd:
                return "found", 0
            if "docker_services" in cmd:
                return "", 1
            return "", 0

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            # Explicit refresh so the update entity (registered after the sensor)
            # receives the coordinator notification.
            coordinator = hass.data[DOMAIN]["entry1"]
            await coordinator.async_request_refresh()
            await hass.async_block_till_done()

        state = hass.states.get("update.ssh_docker_my_container")
        assert state is not None
        assert state.attributes.get("installed_version") is not None
        assert state.attributes.get("installed_version") == "abc123456789"

    async def test_update_entity_on_when_update_available(self, hass):
        """Update entity state is 'on' when image SHA differs after pull."""
        entry = _make_entry(check_for_updates=True)

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:old111111111", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:new222222222", 0
            if "docker_create" in cmd:
                return "found", 0
            if "docker_services" in cmd:
                return "", 1
            return "", 0

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            # Explicit refresh so update entity receives the notification.
            coordinator = hass.data[DOMAIN]["entry1"]
            await coordinator.async_request_refresh()
            await hass.async_block_till_done()

        assert hass.states.get("update.ssh_docker_my_container").state == "on"

    async def test_update_entity_off_when_no_update(self, hass, mock_ssh):
        entry = _make_entry(check_for_updates=True)
        await _setup_entry(hass, entry)
        # Explicit refresh so the update entity listener is guaranteed to fire.
        coordinator = hass.data[DOMAIN]["entry1"]
        await coordinator.async_request_refresh()
        await hass.async_block_till_done()
        assert hass.states.get("update.ssh_docker_my_container").state == "off"

    async def test_update_install_calls_coordinator_create(self, hass):
        """async_install on the update entity triggers coordinator.create()."""
        entry = _make_entry(entry_id="e1", check_for_updates=True)

        # Use different SHAs so update entity shows "on" (update available).
        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:old111111111", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:new222222222", 0
            if "docker_create" in cmd:
                return "found", 0
            if "docker_services" in cmd:
                return "", 1
            return "", 0

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            coordinator = hass.data[DOMAIN]["e1"]
            await coordinator.async_request_refresh()
            await hass.async_block_till_done()

        assert hass.states.get("update.ssh_docker_my_container").state == "on"

        coordinator.create = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await hass.services.async_call(
                "update", "install",
                {"entity_id": "update.ssh_docker_my_container"},
                blocking=True,
            )
            await hass.async_block_till_done()

        coordinator.create.assert_awaited()

    async def test_installed_and_latest_version_equal_when_no_update(self, hass):
        entry = _make_entry(check_for_updates=True)

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:abc123456789def0", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:abc123456789def0", 0
            if "docker_create" in cmd:
                return "found", 0
            if "docker_services" in cmd:
                return "", 1
            return "", 0

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            coordinator = hass.data[DOMAIN]["entry1"]
            await coordinator.async_request_refresh()
            await hass.async_block_till_done()

        attrs = hass.states.get("update.ssh_docker_my_container").attributes
        assert attrs["installed_version"] == attrs["latest_version"]

    async def test_latest_version_differs_when_update_available(self, hass):
        entry = _make_entry(check_for_updates=True)

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:old111111111aabb", 0
            if "image inspect" in cmd or "docker pull" in cmd:
                return "sha256:new222222222ccdd", 0
            if "docker_create" in cmd:
                return "found", 0
            if "docker_services" in cmd:
                return "", 1
            return "", 0

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)
            coordinator = hass.data[DOMAIN]["entry1"]
            await coordinator.async_request_refresh()
            await hass.async_block_till_done()

        attrs = hass.states.get("update.ssh_docker_my_container").attributes
        assert attrs["installed_version"] != attrs["latest_version"]
        assert attrs["installed_version"] == "old111111111"
        assert attrs["latest_version"] == "new222222222"


# ---------------------------------------------------------------------------
# Entry unload
# ---------------------------------------------------------------------------


class TestEntryUnload:
    """Unloading a config entry tears down its entities and coordinator."""

    async def test_unload_removes_coordinator(self, hass, mock_ssh):
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)
        assert "e1" in hass.data.get(DOMAIN, {})

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        assert "e1" not in hass.data.get(DOMAIN, {})

    async def test_unload_marks_sensor_unavailable(self, hass, mock_ssh):
        """After unload HA marks the sensor state as unavailable (not removes it)."""
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)
        assert hass.states.get("sensor.ssh_docker_my_container").state == "running"

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.ssh_docker_my_container")
        # HA restores entity state as "unavailable" after unload rather than
        # removing the state machine entry.
        assert state is None or state.state == "unavailable"

    async def test_unload_marks_update_unavailable(self, hass, mock_ssh):
        """After unload HA marks the update entity state as unavailable."""
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("update.ssh_docker_my_container")
        assert state is None or state.state == "unavailable"

    async def test_second_entry_unaffected_by_first_unload(self, hass, mock_ssh):
        entry_a = _make_entry(entry_id="ea", name="container_a")
        entry_b = _make_entry(entry_id="eb", name="container_b")
        await _setup_entry(hass, entry_a)
        await _setup_entry(hass, entry_b)

        await hass.config_entries.async_unload(entry_a.entry_id)
        await hass.async_block_till_done()

        assert "ea" not in hass.data.get(DOMAIN, {})
        assert "eb" in hass.data.get(DOMAIN, {})
        assert hass.states.get("sensor.ssh_docker_container_b") is not None


# ---------------------------------------------------------------------------
# Multiple independent entries
# ---------------------------------------------------------------------------


class TestMultipleEntries:
    """Multiple config entries coexist without interfering."""

    async def test_both_sensors_created(self, hass, mock_ssh):
        await _setup_entry(hass, _make_entry(entry_id="ea", name="container_a"))
        await _setup_entry(hass, _make_entry(entry_id="eb", name="container_b"))

        assert hass.states.get("sensor.ssh_docker_container_a") is not None
        assert hass.states.get("sensor.ssh_docker_container_b") is not None

    async def test_both_update_entities_created(self, hass, mock_ssh):
        await _setup_entry(hass, _make_entry(entry_id="ea", name="container_a"))
        await _setup_entry(hass, _make_entry(entry_id="eb", name="container_b"))

        assert hass.states.get("update.ssh_docker_container_a") is not None
        assert hass.states.get("update.ssh_docker_container_b") is not None

    async def test_coordinators_are_independent(self, hass, mock_ssh):
        await _setup_entry(hass, _make_entry(entry_id="ea", name="container_a"))
        await _setup_entry(hass, _make_entry(entry_id="eb", name="container_b"))

        assert hass.data[DOMAIN]["ea"] is not hass.data[DOMAIN]["eb"]

    async def test_service_on_one_entry_does_not_affect_other(self, hass, mock_ssh):
        await _setup_entry(hass, _make_entry(entry_id="ea", name="container_a"))
        await _setup_entry(hass, _make_entry(entry_id="eb", name="container_b"))

        coord_b_refreshed = []
        coord_b = hass.data[DOMAIN]["eb"]
        orig_refresh = coord_b.async_request_refresh

        async def capture():
            coord_b_refreshed.append(True)
            await orig_refresh()

        coord_b.async_request_refresh = capture

        await hass.services.async_call(
            DOMAIN, SERVICE_RESTART,
            {"entity_id": "sensor.ssh_docker_container_a"},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert coord_b_refreshed == []


# ---------------------------------------------------------------------------
# Coordinator pending state
# ---------------------------------------------------------------------------


class TestPendingState:
    """Coordinator pending state is surfaced through the sensor."""

    async def test_pending_state_reflected_by_sensor(self, hass, mock_ssh):
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["e1"]
        coordinator.set_pending_state("restarting")
        await hass.async_block_till_done()

        assert hass.states.get("sensor.ssh_docker_my_container").state == "restarting"

    async def test_pending_state_cleared_after_refresh(self, hass, mock_ssh):
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["e1"]
        coordinator.set_pending_state("restarting")
        await coordinator.async_request_refresh()
        await hass.async_block_till_done()

        assert coordinator._pending_state is None
        assert hass.states.get("sensor.ssh_docker_my_container").state == "running"


# ---------------------------------------------------------------------------
# Service name vs. display name
# ---------------------------------------------------------------------------


class TestServiceVsName:
    """entry.data['service'] is used in docker commands; 'name' is the display label."""

    async def test_service_used_in_docker_inspect(self, hass):
        entry = _make_entry(name="My Nginx", service="nginx_container")
        commands_seen = []

        async def mock_run(h, opts, cmd, timeout=60):
            commands_seen.append(cmd)
            return await _default_ssh_run(h, opts, cmd, timeout)

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        inspect_cmds = [c for c in commands_seen if "inspect" in c and "image" not in c]
        assert any("nginx_container" in c for c in inspect_cmds), (
            f"Expected 'nginx_container' in inspect commands; got {inspect_cmds}"
        )

    async def test_sensor_name_attribute_uses_display_name(self, hass):
        entry = _make_entry(name="My Nginx", service="nginx_container")

        async def mock_run(h, opts, cmd, timeout=60):
            if "docker inspect" in cmd and "image inspect" not in cmd:
                return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:abc123456789", 0
            if "docker_create" in cmd:
                return "found", 0
            return "", 1

        with patch("custom_components.ssh_docker.coordinator._ssh_run", side_effect=mock_run), \
             patch("custom_components.ssh_docker._ssh_run", side_effect=mock_run):
            await _setup_entry(hass, entry)

        state = hass.states.get("sensor.ssh_docker_my_nginx")
        assert state is not None
        assert state.attributes["name"] == "My Nginx"

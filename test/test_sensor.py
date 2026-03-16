"""Tests for the SSH Docker sensor platform."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_docker.sensor import DockerContainerSensor  # noqa: E402
from ssh_docker.coordinator import SshDockerCoordinator, STATE_UNAVAILABLE, STATE_UNKNOWN  # noqa: E402
from ssh_docker.const import (  # noqa: E402
    CONF_UPDATE_AVAILABLE, CONF_CREATED, CONF_IMAGE, CONF_AUTO_UPDATE,
    CONF_CHECK_FOR_UPDATES, DEFAULT_TIMEOUT,
)
from homeassistant.config_entries import ConfigEntry  # noqa: E402
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED  # noqa: E402
from homeassistant.core import CoreState  # noqa: E402


def _make_sensor(container_name="my_container", options=None):
    """Create a SshDockerCoordinator + DockerContainerSensor with mocked dependencies."""
    if options is None:
        options = {
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
            "docker_command": "docker",
            "check_known_hosts": True,
            "auto_update": False,
        }
    entry = ConfigEntry(
        entry_id="test_id",
        data={"name": container_name, "service": container_name},
        options=options,
    )
    mock_hass = MagicMock()
    mock_hass.state = "running"  # CoreState.running == "running"
    coordinator = SshDockerCoordinator(entry=entry, hass=mock_hass)
    sensor = DockerContainerSensor(coordinator, entry, mock_hass)
    sensor.hass = mock_hass
    return coordinator, sensor


class TestDockerContainerSensor(unittest.IsolatedAsyncioTestCase):
    """Test the DockerContainerSensor entity."""

    def setUp(self):
        """Clear the docker_create availability cache before each test."""
        import ssh_docker.coordinator as coordinator_module
        coordinator_module._DOCKER_CREATE_CACHE.clear()

    async def test_initial_state_is_unknown(self):
        """Test that the initial state before any update is 'unknown'."""
        coordinator, sensor = _make_sensor()
        self.assertEqual(sensor.native_value, STATE_UNKNOWN)

    async def test_update_sets_running_state(self):
        """Test that a successful inspect returns the running state."""
        coordinator, sensor = _make_sensor()
        call_count = 0

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:abc123", 0
            return "sha256:abc123", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(sensor.native_value, "running")
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs[CONF_IMAGE], "nginx:latest")
        self.assertEqual(attrs[CONF_CREATED], "2023-01-01T00:00:00Z")
        self.assertFalse(attrs[CONF_UPDATE_AVAILABLE])
        self.assertEqual(attrs["host"], "192.168.1.100")

    async def test_update_sets_unavailable_when_container_not_found(self):
        """Test that a failed inspect sets the state to unavailable."""
        coordinator, sensor = _make_sensor()

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            return "", 1

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(sensor.native_value, STATE_UNAVAILABLE)
        self.assertEqual(
            sensor.extra_state_attributes,
            {"name": "my_container", "host": "192.168.1.100", "docker_create_available": False},
        )

    async def test_update_sets_unavailable_on_exception(self):
        """Test that an exception during SSH sets the state to unavailable."""
        coordinator, sensor = _make_sensor()

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            raise OSError("Connection refused")

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(sensor.native_value, STATE_UNAVAILABLE)

    async def test_update_detects_newer_image(self):
        """Test that a different image ID is detected as an available update."""
        coordinator, sensor = _make_sensor(options={
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
            "docker_command": "docker",
            "check_known_hosts": True,
            "auto_update": False,
            CONF_CHECK_FOR_UPDATES: True,
        })
        call_count = 0

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:old123", 0
            return "sha256:new456", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(sensor.native_value, "running")
        self.assertTrue(sensor.extra_state_attributes[CONF_UPDATE_AVAILABLE])

    async def test_update_no_update_when_image_unchanged(self):
        """Test that the same image ID does not trigger an update flag."""
        coordinator, sensor = _make_sensor()
        call_count = 0

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:abc123", 0
            return "sha256:abc123", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertFalse(sensor.extra_state_attributes[CONF_UPDATE_AVAILABLE])

    async def test_auto_update_triggers_recreate(self):
        """Test that auto-update calls docker_create when an update is available."""
        options = {
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
            "docker_command": "docker",
            "check_known_hosts": True,
            CONF_AUTO_UPDATE: True,
            CONF_CHECK_FOR_UPDATES: True,
        }
        coordinator, sensor = _make_sensor(options=options)
        call_count = 0

        async def mock_ssh_run(hass, opts, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # docker inspect - container running with old image
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:old123", 0
            if call_count == 2:
                # docker pull + inspect - new image available
                return "sha256:new456", 0
            if call_count == 3:
                # check if docker_create exists
                return "found", 0
            if call_count == 4:
                # docker_create execution
                return "", 0
            # follow-up refresh: container now runs new image
            if call_count == 5:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:new456", 0
            return "sha256:new456", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(call_count, 6)

    async def test_auto_update_schedules_refresh_after_successful_recreate(self):
        """Test that async_request_refresh is awaited after a successful auto-recreate."""
        options = {
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
            "docker_command": "docker",
            "check_known_hosts": True,
            CONF_AUTO_UPDATE: True,
            CONF_CHECK_FOR_UPDATES: True,
        }
        coordinator, sensor = _make_sensor(options=options)
        call_count = 0

        async def mock_ssh_run(hass, opts, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:old123", 0
            if call_count == 2:
                return "sha256:new456", 0
            if call_count == 3:
                return "found", 0
            if call_count == 4:
                # docker_create execution succeeds
                return "", 0
            # follow-up refresh: container now runs new image
            if call_count == 5:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:new456", 0
            return "sha256:new456", 0

        with patch.object(coordinator, "async_request_refresh", wraps=coordinator.async_request_refresh) as mock_refresh:
            with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
                await sensor.async_update()

        # async_request_refresh is called twice: once by sensor.async_update(), once as follow-up after recreate
        self.assertEqual(mock_refresh.call_count, 2)
        # After successful recreate the coordinator data should show no update available
        self.assertFalse(coordinator.data["update_available"])

    async def test_auto_update_schedules_refresh_even_when_recreate_fails(self):
        """Test that a refresh is still awaited even when auto-recreate fails."""
        options = {
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
            "docker_command": "docker",
            "check_known_hosts": True,
            CONF_AUTO_UPDATE: True,
            CONF_CHECK_FOR_UPDATES: True,
        }
        coordinator, sensor = _make_sensor(options=options)
        call_count = 0

        async def mock_ssh_run(hass, opts, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:old123", 0
            if call_count == 2:
                return "sha256:new456", 0
            if call_count == 3:
                # docker_create exists check
                return "found", 0
            if call_count == 4:
                # docker_create execution fails
                return "", 1
            # follow-up refresh: container still runs old image
            if call_count == 5:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:old123", 0
            return "sha256:new456", 0

        with patch.object(coordinator, "async_request_refresh", wraps=coordinator.async_request_refresh) as mock_refresh:
            with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
                await sensor.async_update()

        # async_request_refresh is called twice: once by sensor.async_update(), once as follow-up
        self.assertEqual(mock_refresh.call_count, 2)

    async def test_auto_update_sets_recreating_pending_state(self):
        """Test that auto-update sets a 'recreating' pending state before calling docker_create."""
        options = {
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
            "docker_command": "docker",
            "check_known_hosts": True,
            CONF_AUTO_UPDATE: True,
            CONF_CHECK_FOR_UPDATES: True,
        }
        coordinator, sensor = _make_sensor(options=options)
        call_count = 0
        observed_pending_states = []

        original_auto_recreate = coordinator._auto_recreate

        async def mock_auto_recreate(*args, **kwargs):
            observed_pending_states.append(coordinator._pending_state)
            await original_auto_recreate(*args, **kwargs)

        async def mock_ssh_run(hass, opts, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:old123", 0
            if call_count == 2:
                return "sha256:new456", 0
            if call_count == 3:
                return "found", 0
            if call_count == 4:
                return "", 0
            if call_count == 5:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:new456", 0
            return "sha256:new456", 0

        with patch.object(coordinator, "_auto_recreate", mock_auto_recreate):
            with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
                await sensor.async_update()

        self.assertEqual(observed_pending_states, ["recreating"])

    async def test_auto_update_skips_when_docker_create_missing(self):
        """Test that auto-update logs a warning when docker_create is not found."""
        options = {
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
            "docker_command": "docker",
            "check_known_hosts": True,
            CONF_AUTO_UPDATE: True,
            CONF_CHECK_FOR_UPDATES: True,
        }
        coordinator, sensor = _make_sensor(options=options)
        call_count = 0

        async def mock_ssh_run(hass, opts, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:old123", 0
            if call_count == 2:
                return "sha256:new456", 0
            # docker_create not found (call 3) and any further calls
            return "not_found", 0

        with patch.object(coordinator, "async_request_refresh", wraps=coordinator.async_request_refresh) as mock_refresh:
            with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
                await sensor.async_update()

        # async_request_refresh is called twice: once by sensor.async_update(), once as follow-up
        self.assertEqual(mock_refresh.call_count, 2)

    async def test_pending_state_returned_by_native_value(self):
        """Test that a pending state set on coordinator is reflected by the sensor."""
        coordinator, sensor = _make_sensor()
        coordinator.set_pending_state("restarting")
        self.assertEqual(sensor.native_value, "restarting")

    async def test_pending_state_cleared_after_refresh(self):
        """Test that pending state is cleared once a real fetch completes."""
        coordinator, sensor = _make_sensor()
        coordinator.set_pending_state("restarting")

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:abc123", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertIsNone(coordinator._pending_state)
        self.assertEqual(sensor.native_value, "running")

    async def test_update_notifies_listeners(self):
        """Test that async_update calls coordinator listeners after fetching data."""
        coordinator, sensor = _make_sensor()
        listener_called = []

        coordinator.async_add_listener(lambda: listener_called.append(True))

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:abc123", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertTrue(listener_called)


class TestAsyncAddedToHass(unittest.IsolatedAsyncioTestCase):
    """Test the async_added_to_hass lifecycle method."""

    def setUp(self):
        """Clear the docker_create availability cache before each test."""
        import ssh_docker.coordinator as coordinator_module
        coordinator_module._DOCKER_CREATE_CACHE.clear()

    def _make_sensor_with_hass_state(self, hass_state, container_name="my_container"):
        """Create a sensor with a mocked hass at the given state."""
        options = {
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
            "docker_command": "docker",
            "check_known_hosts": True,
        }
        entry = ConfigEntry(
            entry_id="test_id",
            data={"name": container_name, "service": container_name},
            options=options,
        )
        mock_hass = MagicMock()
        mock_hass.state = hass_state
        mock_hass.config_entries.async_entries.return_value = [entry]
        coordinator = SshDockerCoordinator(entry=entry, hass=mock_hass)
        sensor = DockerContainerSensor(coordinator, entry, mock_hass)
        sensor.hass = mock_hass
        return sensor

    async def test_async_added_to_hass_when_ha_running_creates_task(self):
        """When HA is already running, async_added_to_hass should create an async task."""
        sensor = self._make_sensor_with_hass_state(CoreState.running)
        with patch.object(sensor, "async_update_ha_state", new=AsyncMock()):
            await sensor.async_added_to_hass()

        sensor.hass.async_create_task.assert_called_once()
        sensor.hass.bus.async_listen_once.assert_not_called()

    async def test_async_added_to_hass_when_ha_starting_registers_listener(self):
        """When HA is starting, async_added_to_hass should register a one-shot event listener."""
        sensor = self._make_sensor_with_hass_state(CoreState.starting)
        with patch.object(sensor, "async_update_ha_state", new=AsyncMock()):
            await sensor.async_added_to_hass()

        sensor.hass.bus.async_listen_once.assert_called_once()
        sensor.hass.async_create_task.assert_not_called()
        event_name = sensor.hass.bus.async_listen_once.call_args[0][0]
        self.assertEqual(event_name, EVENT_HOMEASSISTANT_STARTED)

    async def test_async_added_to_hass_sets_initializing_pending_state(self):
        """Test that async_added_to_hass sets an 'initializing' pending state immediately."""
        sensor = self._make_sensor_with_hass_state(CoreState.running)
        with patch.object(sensor, "async_update_ha_state", new=AsyncMock()):
            await sensor.async_added_to_hass()

        self.assertEqual(sensor.native_value, "initializing")


if __name__ == "__main__":
    unittest.main()

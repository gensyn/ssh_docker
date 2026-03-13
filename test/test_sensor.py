"""Tests for the SSH Docker sensor platform."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_docker.sensor import DockerContainerSensor, STATE_UNAVAILABLE  # noqa: E402
from ssh_docker.const import (  # noqa: E402
    CONF_UPDATE_AVAILABLE, CONF_CREATED, CONF_IMAGE, CONF_AUTO_UPDATE,
    CONF_CHECK_FOR_UPDATES, DEFAULT_TIMEOUT,
)
from homeassistant.config_entries import ConfigEntry  # noqa: E402


def _make_sensor(container_name="my_container", options=None):
    """Create a DockerContainerSensor with mocked dependencies."""
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
    sensor = DockerContainerSensor(entry, mock_hass)
    sensor.hass = mock_hass
    return sensor


class TestDockerContainerSensor(unittest.IsolatedAsyncioTestCase):
    """Test the DockerContainerSensor entity."""

    def setUp(self):
        """Clear the docker_create availability cache before each test."""
        import ssh_docker.sensor as sensor_module
        sensor_module._DOCKER_CREATE_CACHE.clear()

    async def test_update_sets_running_state(self):
        """Test that a successful inspect returns the running state."""
        sensor = _make_sensor()
        call_count = 0

        async def mock_ssh_run(hass, options, command):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:abc123", 0
            return "sha256:abc123", 0

        with patch("ssh_docker.sensor._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(sensor._attr_native_value, "running")
        self.assertEqual(sensor._attr_extra_state_attributes[CONF_IMAGE], "nginx:latest")
        self.assertEqual(sensor._attr_extra_state_attributes[CONF_CREATED], "2023-01-01T00:00:00Z")
        self.assertFalse(sensor._attr_extra_state_attributes[CONF_UPDATE_AVAILABLE])
        self.assertEqual(sensor._attr_extra_state_attributes["host"], "192.168.1.100")

    async def test_update_sets_unavailable_when_container_not_found(self):
        """Test that a failed inspect sets the state to unavailable."""
        sensor = _make_sensor()

        async def mock_ssh_run(hass, options, command):
            return "", 1

        with patch("ssh_docker.sensor._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(sensor._attr_native_value, STATE_UNAVAILABLE)
        self.assertEqual(
            sensor._attr_extra_state_attributes,
            {"name": "my_container", "host": "192.168.1.100", "docker_create_available": False},
        )

    async def test_update_sets_unavailable_on_exception(self):
        """Test that an exception during SSH sets the state to unavailable."""
        sensor = _make_sensor()

        async def mock_ssh_run(hass, options, command):
            raise OSError("Connection refused")

        with patch("ssh_docker.sensor._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(sensor._attr_native_value, STATE_UNAVAILABLE)

    async def test_update_detects_newer_image(self):
        """Test that a different image ID is detected as an available update."""
        sensor = _make_sensor(options={
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

        with patch("ssh_docker.sensor._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(sensor._attr_native_value, "running")
        self.assertTrue(sensor._attr_extra_state_attributes[CONF_UPDATE_AVAILABLE])

    async def test_update_no_update_when_image_unchanged(self):
        """Test that the same image ID does not trigger an update flag."""
        sensor = _make_sensor()
        call_count = 0

        async def mock_ssh_run(hass, options, command):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:abc123", 0
            return "sha256:abc123", 0

        with patch("ssh_docker.sensor._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertFalse(sensor._attr_extra_state_attributes[CONF_UPDATE_AVAILABLE])

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
        sensor = _make_sensor(options=options)
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
            # docker_create execution
            return "", 0

        with patch("ssh_docker.sensor._ssh_run", mock_ssh_run):
            await sensor.async_update()

        self.assertEqual(call_count, 4)
        self.assertTrue(sensor._attr_extra_state_attributes[CONF_UPDATE_AVAILABLE])

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
        sensor = _make_sensor(options=options)
        call_count = 0

        async def mock_ssh_run(hass, opts, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "running;2023-01-01T00:00:00Z;nginx:latest;sha256:old123", 0
            if call_count == 2:
                return "sha256:new456", 0
            # docker_create not found
            return "not_found", 0

        with patch("ssh_docker.sensor._ssh_run", mock_ssh_run):
            await sensor.async_update()

        # Should stop after checking for docker_create (3 calls total)
        self.assertEqual(call_count, 3)


if __name__ == "__main__":
    unittest.main()

"""Tests for the SSH Docker update platform."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_docker.update import DockerContainerUpdateEntity  # noqa: E402
from ssh_docker.const import (  # noqa: E402
    DOMAIN, DOCKER_CREATE_EXECUTABLE, DEFAULT_TIMEOUT,
)
from homeassistant.config_entries import ConfigEntry  # noqa: E402


def _make_update_entity(container_name="my_container", options=None):
    """Create a DockerContainerUpdateEntity with mocked dependencies."""
    if options is None:
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
    entity = DockerContainerUpdateEntity(entry, mock_hass)
    entity.hass = mock_hass
    return entity


class TestDockerContainerUpdateEntity(unittest.TestCase):
    """Unit tests for DockerContainerUpdateEntity state helpers."""

    def test_initial_state_is_none(self):
        """Installed and latest version should be None before any sensor update."""
        entity = _make_update_entity()
        self.assertIsNone(entity._attr_installed_version)
        self.assertIsNone(entity._attr_latest_version)

    def test_set_update_state_no_update(self):
        """When update_available=False the installed and latest version should match."""
        entity = _make_update_entity()
        entity.set_update_state(False, "nginx:latest")
        self.assertEqual(entity._attr_installed_version, "nginx:latest")
        self.assertEqual(entity._attr_latest_version, "nginx:latest")

    def test_set_update_state_update_available(self):
        """When update_available=True the latest version should differ from installed."""
        entity = _make_update_entity()
        entity.set_update_state(True, "nginx:latest")
        self.assertEqual(entity._attr_installed_version, "nginx:latest")
        self.assertNotEqual(entity._attr_latest_version, entity._attr_installed_version)
        self.assertIn("nginx:latest", entity._attr_latest_version)

    def test_set_update_state_unavailable_clears_versions(self):
        """When the container is unreachable (image_name=None) both versions become None."""
        entity = _make_update_entity()
        # First mark an update as available...
        entity.set_update_state(True, "nginx:latest")
        # ...then mark the container as unreachable
        entity.set_update_state(False, None)
        self.assertIsNone(entity._attr_installed_version)
        self.assertIsNone(entity._attr_latest_version)

    def test_unique_id(self):
        """Unique ID should end with '_update'."""
        entity = _make_update_entity()
        self.assertTrue(entity._attr_unique_id.endswith("_update"))

    def test_entity_id_format(self):
        """entity_id should follow the update.ssh_docker_{name} pattern."""
        entity = _make_update_entity(container_name="my_container")
        self.assertIn("ssh_docker_", entity.entity_id)
        self.assertTrue(entity.entity_id.startswith("update."))

    def test_title_equals_container_name(self):
        """Title should equal the container name."""
        entity = _make_update_entity(container_name="my_container")
        self.assertEqual(entity._attr_title, "my_container")

    def test_device_info_uses_entry_id(self):
        """Device info identifiers should include the domain and entry_id."""
        entity = _make_update_entity()
        self.assertIn((DOMAIN, "test_id"), entity._attr_device_info.identifiers)

    def test_set_update_state_writes_ha_state(self):
        """set_update_state should call async_write_ha_state."""
        entity = _make_update_entity()
        with patch.object(entity, "async_write_ha_state") as mock_write:
            entity.set_update_state(True, "nginx:latest")
        mock_write.assert_called_once()


class TestDockerContainerUpdateEntityInstall(unittest.IsolatedAsyncioTestCase):
    """Async tests for DockerContainerUpdateEntity.async_install."""

    async def test_install_runs_docker_create(self):
        """async_install should run docker_create on the remote host."""
        entity = _make_update_entity()
        call_count = 0

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # docker_create availability check
                return "found", 0
            # docker_create execution
            return "", 0

        with patch("ssh_docker.update._ssh_run", mock_ssh_run):
            await entity.async_install(None, False)

        self.assertEqual(call_count, 2)

    async def test_install_resets_in_progress(self):
        """in_progress flag should be False after install completes."""
        entity = _make_update_entity()

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            return "found", 0

        with patch("ssh_docker.update._ssh_run", mock_ssh_run):
            await entity.async_install(None, False)

        self.assertFalse(entity._attr_in_progress)

    async def test_install_resets_in_progress_on_error(self):
        """in_progress flag should be False even when docker_create is not found."""
        entity = _make_update_entity()

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            return "not_found", 0

        from homeassistant.exceptions import ServiceValidationError
        with patch("ssh_docker.update._ssh_run", mock_ssh_run):
            with self.assertRaises(ServiceValidationError):
                await entity.async_install(None, False)

        self.assertFalse(entity._attr_in_progress)

    async def test_install_schedules_sensor_refresh(self):
        """async_install should ask the sensor to refresh after completion."""
        entity = _make_update_entity()
        mock_sensor = MagicMock()
        entity.hass.data = {DOMAIN: {"test_id": mock_sensor, "test_id_update": entity}}
        call_count = 0

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "found", 0
            return "", 0

        with patch("ssh_docker.update._ssh_run", mock_ssh_run):
            await entity.async_install(None, False)

        mock_sensor.async_schedule_update_ha_state.assert_called_once_with(force_refresh=True)

    async def test_install_raises_when_docker_create_missing(self):
        """async_install should raise ServiceValidationError when docker_create is absent."""
        entity = _make_update_entity()

        async def mock_ssh_run(hass, options, command, timeout=DEFAULT_TIMEOUT):
            return "not_found", 0

        from homeassistant.exceptions import ServiceValidationError
        with patch("ssh_docker.update._ssh_run", mock_ssh_run):
            with self.assertRaises(ServiceValidationError):
                await entity.async_install(None, False)


if __name__ == "__main__":
    unittest.main()

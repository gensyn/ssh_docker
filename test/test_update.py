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
from ssh_docker.coordinator import SshDockerCoordinator, STATE_UNKNOWN  # noqa: E402
from ssh_docker.const import (  # noqa: E402
    DOMAIN, DEFAULT_TIMEOUT,
)
from homeassistant.config_entries import ConfigEntry  # noqa: E402


def _make_update_entity(container_name="my_container", options=None):
    """Create a DockerContainerUpdateEntity with a mocked coordinator."""
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
    coordinator = SshDockerCoordinator(entry=entry, hass=mock_hass)
    mock_hass.data = {DOMAIN: {entry.entry_id: coordinator}}
    entity = DockerContainerUpdateEntity(coordinator, entry, mock_hass)
    entity.hass = mock_hass
    return entity, coordinator


class TestDockerContainerUpdateEntity(unittest.TestCase):
    """Unit tests for DockerContainerUpdateEntity state helpers."""

    def test_initial_state_is_none(self):
        """Installed and latest version should be None before any coordinator update."""
        entity, _ = _make_update_entity()
        self.assertIsNone(entity._attr_installed_version)
        self.assertIsNone(entity._attr_latest_version)

    def test_set_update_state_no_update(self):
        """When update_available=False the installed and latest version should match."""
        entity, _ = _make_update_entity()
        entity.set_update_state(False, "sha256:abc123456789def0", None)
        self.assertEqual(entity._attr_installed_version, "abc123456789")
        self.assertEqual(entity._attr_latest_version, "abc123456789")

    def test_set_update_state_update_available(self):
        """When update_available=True the latest version should differ from installed."""
        entity, _ = _make_update_entity()
        entity.set_update_state(True, "sha256:abc123456789def0", "sha256:def456789012abc0")
        self.assertEqual(entity._attr_installed_version, "abc123456789")
        self.assertEqual(entity._attr_latest_version, "def456789012")
        self.assertNotEqual(entity._attr_latest_version, entity._attr_installed_version)

    def test_set_update_state_unavailable_clears_versions(self):
        """When the container is unreachable (installed_image_id=None) both versions become None."""
        entity, _ = _make_update_entity()
        # First mark an update as available...
        entity.set_update_state(True, "sha256:abc123456789def0", "sha256:def456789012abc0")
        # ...then mark the container as unreachable
        entity.set_update_state(False, None)
        self.assertIsNone(entity._attr_installed_version)
        self.assertIsNone(entity._attr_latest_version)

    def test_unique_id(self):
        """Unique ID should end with '_update'."""
        entity, _ = _make_update_entity()
        self.assertTrue(entity._attr_unique_id.endswith("_update"))

    def test_entity_id_format(self):
        """entity_id should follow the update.ssh_docker_{name} pattern."""
        entity, _ = _make_update_entity(container_name="my_container")
        self.assertIn("ssh_docker_", entity.entity_id)
        self.assertTrue(entity.entity_id.startswith("update."))

    def test_title_equals_container_name(self):
        """Title should equal the container name."""
        entity, _ = _make_update_entity(container_name="my_container")
        self.assertEqual(entity._attr_title, "my_container")

    def test_device_info_uses_entry_id(self):
        """Device info identifiers should include the domain and entry_id."""
        entity, _ = _make_update_entity()
        self.assertIn((DOMAIN, "test_id"), entity._attr_device_info.identifiers)

    def test_set_update_state_writes_ha_state(self):
        """set_update_state should call async_write_ha_state."""
        entity, _ = _make_update_entity()
        with patch.object(entity, "async_write_ha_state") as mock_write:
            entity.set_update_state(True, "sha256:abc123456789def0", "sha256:def456789012abc0")
        mock_write.assert_called_once()

    def test_coordinator_listener_updates_state(self):
        """When the coordinator notifies, update entity should update its own state."""
        entity, coordinator = _make_update_entity()
        # Simulate coordinator data after a successful fetch
        coordinator.data = {
            "state": "running",
            "attributes": {},
            "update_available": True,
            "installed_image_id": "sha256:abc123456789def0",
            "latest_image_id": "sha256:def456789012abc0",
        }
        with patch.object(entity, "async_write_ha_state"):
            entity._handle_coordinator_update()
        self.assertEqual(entity._attr_installed_version, "abc123456789")
        self.assertEqual(entity._attr_latest_version, "def456789012")


class TestDockerContainerUpdateEntityInstall(unittest.IsolatedAsyncioTestCase):
    """Async tests for DockerContainerUpdateEntity.async_install."""

    async def test_install_calls_coordinator_create(self):
        """async_install should call coordinator.create()."""
        entity, coordinator = _make_update_entity()
        coordinator.create = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        await entity.async_install(None, False)

        coordinator.create.assert_awaited_once()

    async def test_install_resets_in_progress(self):
        """in_progress flag should be False after install completes."""
        entity, coordinator = _make_update_entity()
        coordinator.create = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        await entity.async_install(None, False)

        self.assertFalse(entity._attr_in_progress)

    async def test_install_resets_in_progress_on_error(self):
        """in_progress flag should be False even when coordinator.create() raises."""
        entity, coordinator = _make_update_entity()
        from homeassistant.exceptions import ServiceValidationError
        coordinator.create = AsyncMock(
            side_effect=ServiceValidationError("docker_create not found on host")
        )
        coordinator.async_request_refresh = AsyncMock()

        with self.assertRaises(ServiceValidationError):
            await entity.async_install(None, False)

        self.assertFalse(entity._attr_in_progress)

    async def test_install_requests_coordinator_refresh(self):
        """async_install should call coordinator.async_request_refresh() after completion."""
        entity, coordinator = _make_update_entity()
        coordinator.create = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        await entity.async_install(None, False)

        coordinator.async_request_refresh.assert_awaited_once()

    async def test_install_raises_when_coordinator_create_fails(self):
        """async_install should propagate ServiceValidationError from coordinator.create()."""
        entity, coordinator = _make_update_entity()
        from homeassistant.exceptions import ServiceValidationError
        coordinator.create = AsyncMock(
            side_effect=ServiceValidationError("docker_create not found on host")
        )
        coordinator.async_request_refresh = AsyncMock()

        with self.assertRaises(ServiceValidationError):
            await entity.async_install(None, False)


if __name__ == "__main__":
    unittest.main()

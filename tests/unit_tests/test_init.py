"""Tests for the SSH Docker integration __init__.py setup."""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_docker import async_setup, async_setup_entry  # noqa: E402
from ssh_docker.const import (  # noqa: E402
    DOMAIN, SERVICE_CREATE, SERVICE_RESTART, SERVICE_STOP, SERVICE_REMOVE, SERVICE_REFRESH,
    SERVICE_GET_LOGS, SERVICE_EXECUTE_COMMAND, DEFAULT_TIMEOUT,
)
from ssh_docker.frontend import SshDockerPanelRegistration  # noqa: E402
from homeassistant.config_entries import ConfigEntry  # noqa: E402


class TestAsyncSetup(unittest.IsolatedAsyncioTestCase):
    """Test the async_setup function."""

    async def test_services_are_registered(self):
        """Test that all four Docker services are registered during setup."""
        mock_hass = MagicMock()
        mock_hass.services = MagicMock()
        mock_hass.services.async_register = MagicMock()

        with patch("ssh_docker.SshDockerPanelRegistration") as mock_panel_cls:
            mock_panel_cls.return_value.async_register = AsyncMock()
            result = await async_setup(mock_hass, {})

        self.assertTrue(result)
        registered_calls = mock_hass.services.async_register.call_args_list
        self.assertEqual(len(registered_calls), 7)

        service_names = [call.args[1] for call in registered_calls]
        self.assertIn(SERVICE_CREATE, service_names)
        self.assertIn(SERVICE_RESTART, service_names)
        self.assertIn(SERVICE_STOP, service_names)
        self.assertIn(SERVICE_REMOVE, service_names)
        self.assertIn(SERVICE_REFRESH, service_names)
        self.assertIn(SERVICE_GET_LOGS, service_names)
        self.assertIn(SERVICE_EXECUTE_COMMAND, service_names)

        domains = [call.args[0] for call in registered_calls]
        for domain in domains:
            self.assertEqual(domain, DOMAIN)

    async def test_setup_returns_true(self):
        """Test that async_setup returns True on success."""
        mock_hass = MagicMock()
        mock_hass.services = MagicMock()
        mock_hass.services.async_register = MagicMock()

        with patch("ssh_docker.SshDockerPanelRegistration") as mock_panel_cls:
            mock_panel_cls.return_value.async_register = AsyncMock()
            result = await async_setup(mock_hass, {})

        self.assertTrue(result)

    async def test_panel_registration_is_called(self):
        """Test that the panel registration is called during async_setup."""
        mock_hass = MagicMock()
        mock_hass.services = MagicMock()
        mock_hass.services.async_register = MagicMock()

        with patch("ssh_docker.SshDockerPanelRegistration") as mock_panel_cls:
            mock_register = AsyncMock()
            mock_panel_cls.return_value.async_register = mock_register
            await async_setup(mock_hass, {})

        mock_panel_cls.assert_called_once_with(mock_hass)
        mock_register.assert_awaited_once()


class TestSshDockerPanelRegistration(unittest.IsolatedAsyncioTestCase):
    """Test SshDockerPanelRegistration sidebar panel registration."""

    def _make_hass(self) -> MagicMock:
        """Build a minimal hass mock."""
        hass = MagicMock()
        hass.data = {}
        hass.http.async_register_static_paths = AsyncMock()
        return hass

    async def test_async_register_panel_is_called(self):
        """Test that async_register_panel is called with the correct arguments."""
        hass = self._make_hass()
        registration = SshDockerPanelRegistration(hass)

        with patch(
            "ssh_docker.frontend.SshDockerPanelRegistration._async_register_path",
            new=AsyncMock(),
        ), patch(
            "ssh_docker.frontend.async_register_panel",
            new=AsyncMock(),
        ) as mock_register_panel:
            await registration._async_register_panel()

        mock_register_panel.assert_awaited_once()
        call_kwargs = mock_register_panel.call_args.kwargs
        self.assertEqual(call_kwargs["webcomponent_name"], "ssh-docker-panel")
        self.assertEqual(call_kwargs["sidebar_title"], "SSH Docker")
        self.assertEqual(call_kwargs["sidebar_icon"], "mdi:docker")
        self.assertEqual(call_kwargs["frontend_url_path"], "ssh-docker")
        self.assertIn("module_url", call_kwargs)
        self.assertIn("ssh-docker-panel.js", call_kwargs["module_url"])

    async def test_async_register_panel_handles_duplicate(self):
        """Test that duplicate panel registration (HomeAssistantError) raises no exception."""
        from homeassistant.exceptions import HomeAssistantError  # noqa: PLC0415
        hass = self._make_hass()
        registration = SshDockerPanelRegistration(hass)

        with patch(
            "ssh_docker.frontend.async_register_panel",
            new=AsyncMock(side_effect=HomeAssistantError("Panel already registered")),
        ), self.assertLogs("ssh_docker.frontend", level="DEBUG") as log_ctx:
            # Should not raise
            await registration._async_register_panel()

        self.assertTrue(
            any("already registered" in msg for msg in log_ctx.output),
            "Expected 'already registered' in debug log",
        )


def _make_entry(service="my_container", host="192.168.1.100"):
    """Build a minimal ConfigEntry for setup-entry tests."""
    return ConfigEntry(
        entry_id="test_entry_id",
        data={"name": service, "service": service},
        options={
            "host": host,
            "username": "user",
            "password": "pass",
            "docker_command": "docker",
            "check_known_hosts": True,
        },
    )


def _make_hass_for_setup():
    """Build a minimal hass mock suitable for async_setup_entry tests."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    # Close any coroutine passed in to prevent "never awaited" RuntimeWarnings.
    hass.async_create_task = lambda coro, *a, **kw: coro.close()
    return hass


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):
    """Test async_setup_entry, specifically the docker_services availability check."""

    def setUp(self):
        """Clear the docker_services cache before each test."""
        import ssh_docker.coordinator as coord_module
        coord_module._DOCKER_SERVICES_CACHE.clear()

    async def test_setup_entry_proceeds_when_service_found_in_json_list(self):
        """Setup succeeds when docker_services returns a JSON list containing the service."""
        entry = _make_entry(service="my_container")
        hass = _make_hass_for_setup()

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            return '["my_container", "other_service"]', 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result = await async_setup_entry(hass, entry)

        self.assertTrue(result)

    async def test_setup_entry_proceeds_when_service_found_in_plain_list(self):
        """Setup succeeds when docker_services returns a plain-text list containing the service."""
        entry = _make_entry(service="my_container")
        hass = _make_hass_for_setup()

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            return "my_container other_service", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result = await async_setup_entry(hass, entry)

        self.assertTrue(result)

    async def test_setup_entry_fails_when_service_absent_from_json_list(self):
        """Setup fails when docker_services returns a JSON list that does not include the service."""
        entry = _make_entry(service="removed_service")
        hass = _make_hass_for_setup()

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            return '["other_service", "another_service"]', 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result = await async_setup_entry(hass, entry)

        self.assertFalse(result)

    async def test_setup_entry_fails_when_service_absent_from_plain_list(self):
        """Setup fails when docker_services returns a plain list that does not include the service."""
        entry = _make_entry(service="removed_service")
        hass = _make_hass_for_setup()

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            return "other_service another_service", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result = await async_setup_entry(hass, entry)

        self.assertFalse(result)

    async def test_setup_entry_proceeds_when_docker_services_not_present(self):
        """Setup proceeds when docker_services is not found (empty output, non-zero exit)."""
        entry = _make_entry(service="my_container")
        hass = _make_hass_for_setup()

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            # docker_services absent: if/elif both false → empty output, exit 1
            return "", 1

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result = await async_setup_entry(hass, entry)

        self.assertTrue(result)

    async def test_setup_entry_proceeds_when_docker_services_returns_empty_output(self):
        """Setup proceeds when docker_services produces empty output with exit 0."""
        entry = _make_entry(service="my_container")
        hass = _make_hass_for_setup()

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            return "", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result = await async_setup_entry(hass, entry)

        self.assertTrue(result)

    async def test_setup_entry_proceeds_on_ssh_error(self):
        """Setup proceeds when SSH raises an exception (can't verify docker_services)."""
        entry = _make_entry(service="my_container")
        hass = _make_hass_for_setup()

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            raise OSError("Connection refused")

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result = await async_setup_entry(hass, entry)

        self.assertTrue(result)

    async def test_setup_entry_proceeds_when_json_list_is_empty(self):
        """Setup proceeds when docker_services returns a JSON empty list."""
        entry = _make_entry(service="my_container")
        hass = _make_hass_for_setup()

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            return "[]", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result = await async_setup_entry(hass, entry)

        self.assertTrue(result)

    async def test_setup_entry_does_not_create_coordinator_when_service_removed(self):
        """No coordinator is stored in hass.data when setup fails due to removed service."""
        entry = _make_entry(service="removed_service")
        hass = _make_hass_for_setup()

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            return '["other_service"]', 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result = await async_setup_entry(hass, entry)

        self.assertFalse(result)
        # hass.data should not contain the coordinator for this entry
        self.assertNotIn(entry.entry_id, hass.data.get(DOMAIN, {}))

    async def test_cache_avoids_second_ssh_call_for_same_host(self):
        """A second entry on the same host reuses the cached docker_services output."""
        entry1 = _make_entry(service="svc1", host="10.0.0.1")
        entry2 = _make_entry(service="svc2", host="10.0.0.1")
        hass = _make_hass_for_setup()
        call_count = 0

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            nonlocal call_count
            call_count += 1
            return '["svc1", "svc2"]', 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await async_setup_entry(hass, entry1)
            await async_setup_entry(hass, entry2)

        # SSH should only be called once for the availability check (one per host)
        self.assertEqual(call_count, 1)

    async def test_cache_is_keyed_per_host(self):
        """Entries on different hosts each trigger their own SSH call."""
        entry_a = _make_entry(service="svc", host="10.0.0.1")
        entry_b = _make_entry(service="svc", host="10.0.0.2")
        hass = _make_hass_for_setup()
        call_count = 0

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            nonlocal call_count
            call_count += 1
            return '["svc"]', 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await async_setup_entry(hass, entry_a)
            await async_setup_entry(hass, entry_b)

        self.assertEqual(call_count, 2)

    async def test_cache_expires_after_ttl(self):
        """An expired cache entry triggers a fresh SSH call."""
        import ssh_docker.coordinator as coord_module
        entry = _make_entry(service="svc", host="10.0.0.1")
        hass = _make_hass_for_setup()
        call_count = 0

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            nonlocal call_count
            call_count += 1
            return '["svc"]', 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await async_setup_entry(hass, entry)

        self.assertEqual(call_count, 1)

        # Manually expire the cache entry
        host = entry.options["host"]
        service_names, _ = coord_module._DOCKER_SERVICES_CACHE[host]
        coord_module._DOCKER_SERVICES_CACHE[host] = (
            service_names,
            time.monotonic() - coord_module._DOCKER_SERVICES_CACHE_TTL - 1,
        )

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            await async_setup_entry(hass, entry)

        self.assertEqual(call_count, 2)

    async def test_cache_stores_none_when_docker_services_absent(self):
        """When docker_services is absent, None is cached and no second SSH call is made."""
        import ssh_docker.coordinator as coord_module
        entry1 = _make_entry(service="svc1", host="10.0.0.3")
        entry2 = _make_entry(service="svc2", host="10.0.0.3")
        hass = _make_hass_for_setup()
        call_count = 0

        async def mock_ssh_run(h, opts, cmd, timeout=60):
            nonlocal call_count
            call_count += 1
            return "", 1  # docker_services not found

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            result1 = await async_setup_entry(hass, entry1)
            result2 = await async_setup_entry(hass, entry2)

        self.assertTrue(result1)
        self.assertTrue(result2)
        self.assertEqual(call_count, 1)
        cached = coord_module._DOCKER_SERVICES_CACHE.get("10.0.0.3")
        self.assertIsNotNone(cached)
        self.assertIsNone(cached[0])  # None means "not found / no output"


class TestExecuteCommandTimeout(unittest.IsolatedAsyncioTestCase):
    """Test that the execute_command service forwards the timeout parameter correctly."""

    async def test_execute_command_uses_default_timeout(self):
        """execute_command uses DEFAULT_TIMEOUT when no timeout is given."""
        from ssh_docker.coordinator import SshDockerCoordinator  # noqa: PLC0415

        entry = _make_entry(service="my_container")
        mock_hass = MagicMock()
        coordinator = SshDockerCoordinator(hass=mock_hass, entry=entry)

        captured_timeout = None

        async def mock_ssh_run(h, opts, cmd, timeout=DEFAULT_TIMEOUT):
            nonlocal captured_timeout
            captured_timeout = timeout
            return "output", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            output, exit_status = await coordinator.execute_command("echo hello")

        self.assertEqual(output, "output")
        self.assertEqual(exit_status, 0)
        self.assertEqual(captured_timeout, DEFAULT_TIMEOUT)

    async def test_execute_command_uses_custom_timeout(self):
        """execute_command forwards a custom timeout to _ssh_run."""
        from ssh_docker.coordinator import SshDockerCoordinator  # noqa: PLC0415

        entry = _make_entry(service="my_container")
        mock_hass = MagicMock()
        coordinator = SshDockerCoordinator(hass=mock_hass, entry=entry)

        captured_timeout = None

        async def mock_ssh_run(h, opts, cmd, timeout=DEFAULT_TIMEOUT):
            nonlocal captured_timeout
            captured_timeout = timeout
            return "custom output", 0

        with patch("ssh_docker.coordinator._ssh_run", mock_ssh_run):
            output, exit_status = await coordinator.execute_command("echo hello", timeout=120)

        self.assertEqual(output, "custom output")
        self.assertEqual(exit_status, 0)
        self.assertEqual(captured_timeout, 120)


if __name__ == "__main__":
    unittest.main()

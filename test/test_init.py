"""Tests for the SSH Docker integration __init__.py setup."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_docker import async_setup  # noqa: E402
from ssh_docker.const import (  # noqa: E402
    DOMAIN, SERVICE_CREATE, SERVICE_RECREATE, SERVICE_START, SERVICE_RESTART,
    SERVICE_STOP, SERVICE_REMOVE, SERVICE_REFRESH,
)
from ssh_docker.frontend import SshDockerPanelRegistration  # noqa: E402


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
        self.assertIn(SERVICE_RECREATE, service_names)
        self.assertIn(SERVICE_START, service_names)
        self.assertIn(SERVICE_RESTART, service_names)
        self.assertIn(SERVICE_STOP, service_names)
        self.assertIn(SERVICE_REMOVE, service_names)
        self.assertIn(SERVICE_REFRESH, service_names)

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


if __name__ == "__main__":
    unittest.main()

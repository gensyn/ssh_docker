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
    DOMAIN, SERVICE_CREATE, SERVICE_RESTART, SERVICE_STOP, SERVICE_REMOVE,
)


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
        self.assertEqual(len(registered_calls), 4)

        service_names = [call.args[1] for call in registered_calls]
        self.assertIn(SERVICE_CREATE, service_names)
        self.assertIn(SERVICE_RESTART, service_names)
        self.assertIn(SERVICE_STOP, service_names)
        self.assertIn(SERVICE_REMOVE, service_names)

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


if __name__ == "__main__":
    unittest.main()

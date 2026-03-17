"""Tests for the SSH Docker options flow."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_docker.options_flow import SshDockerOptionsFlow  # noqa: E402
from homeassistant.config_entries import ConfigEntry  # noqa: E402


class TestSshDockerOptionsFlow(unittest.IsolatedAsyncioTestCase):
    """Test the SSH Docker options flow."""

    def _make_flow(self, current_options=None):
        """Create an options flow instance with a mocked config entry."""
        flow = SshDockerOptionsFlow()
        flow.hass = MagicMock()
        flow.config_entry = ConfigEntry(
            entry_id="test_id",
            data={"name": "my_container"},
            options=current_options or {
                "host": "192.168.1.100",
                "username": "user",
                "password": "pass",
                "docker_command": "docker",
                "check_known_hosts": True,
                "auto_update": False,
            },
        )
        return flow

    async def test_init_step_shows_form_when_no_input(self):
        """Test that the init step shows a form when no input is provided."""
        flow = self._make_flow()

        result = await flow.async_step_init()

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "init")

    async def test_init_step_updates_options_on_valid_input(self):
        """Test that valid input results in updated options."""
        flow = self._make_flow()
        user_input = {
            "host": "192.168.1.200",
            "username": "newuser",
            "password": "newpass",
            "docker_command": "docker",
            "check_known_hosts": True,
            "auto_update": True,
        }
        new_options = {
            "host": "192.168.1.200",
            "username": "newuser",
            "password": "newpass",
            "docker_command": "docker",
            "check_known_hosts": True,
            "auto_update": True,
        }

        with unittest.mock.patch(
            "ssh_docker.options_flow.validate_and_build_options",
            new=AsyncMock(return_value=(new_options, None)),
        ):
            result = await flow.async_step_init(user_input)

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["host"], "192.168.1.200")
        self.assertTrue(result["data"]["auto_update"])

    async def test_init_step_shows_error_on_validation_failure(self):
        """Test that validation failures show an error in the form."""
        flow = self._make_flow()
        user_input = {
            "host": "192.168.1.200",
            "username": "user",
        }

        with unittest.mock.patch(
            "ssh_docker.options_flow.validate_and_build_options",
            new=AsyncMock(return_value=({}, "password_or_key_file_required")),
        ):
            result = await flow.async_step_init(user_input)

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "password_or_key_file_required")


if __name__ == "__main__":
    unittest.main()

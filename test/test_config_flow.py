"""Tests for the SSH Docker config flow."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_docker.config_flow import SshDockerConfigFlow  # noqa: E402
from ssh_docker.const import DOMAIN  # noqa: E402
from homeassistant.config_entries import AbortFlowException  # noqa: E402
from homeassistant.const import CONF_NAME  # noqa: E402


class TestSshDockerConfigFlow(unittest.IsolatedAsyncioTestCase):
    """Test the SSH Docker config flow."""

    def _make_flow(self):
        """Create a flow instance with mocked hass."""
        flow = SshDockerConfigFlow()
        flow.hass = MagicMock()
        flow.context = {}
        return flow

    async def test_user_step_shows_form_when_no_input(self):
        """Test that the user step shows a form when no input is provided."""
        flow = self._make_flow()

        result = await flow.async_step_user()

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")

    async def test_user_step_shows_form_on_error(self):
        """Test that the user step shows a form with errors on validation failure."""
        flow = self._make_flow()
        user_input = {
            CONF_NAME: "my_container",
            "host": "192.168.1.100",
            "username": "user",
        }

        with unittest.mock.patch(
            "ssh_docker.config_flow.validate_and_build_options",
            new=AsyncMock(return_value=({}, "password_or_key_file_required")),
        ):
            result = await flow.async_step_user(user_input)

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "password_or_key_file_required")

    async def test_creates_entry_with_name_in_data(self):
        """Test that a valid submission creates an entry with the name in data."""
        flow = self._make_flow()
        user_input = {
            CONF_NAME: "my_container",
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
        }

        with unittest.mock.patch(
            "ssh_docker.config_flow.validate_and_build_options",
            new=AsyncMock(return_value=({"host": "192.168.1.100"}, None)),
        ):
            result = await flow.async_step_user(user_input)

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "my_container")
        self.assertEqual(result["data"][CONF_NAME], "my_container")

    async def test_shows_error_when_password_key_file_missing(self):
        """Test that an error is shown when neither password nor key_file is provided."""
        flow = self._make_flow()
        user_input = {
            CONF_NAME: "my_container",
            "host": "192.168.1.100",
            "username": "user",
        }

        with unittest.mock.patch(
            "ssh_docker.config_flow.validate_and_build_options",
            new=AsyncMock(return_value=({}, "password_or_key_file_required")),
        ):
            result = await flow.async_step_user(user_input)

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "password_or_key_file_required")

    async def test_shows_error_when_ssh_connection_fails(self):
        """Test that an error is shown when the SSH connection fails."""
        flow = self._make_flow()
        user_input = {
            CONF_NAME: "my_container",
            "host": "192.168.1.100",
            "username": "user",
            "password": "wrong_pass",
        }

        with unittest.mock.patch(
            "ssh_docker.config_flow.validate_and_build_options",
            new=AsyncMock(return_value=({}, "cannot_connect")),
        ):
            result = await flow.async_step_user(user_input)

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "cannot_connect")

    async def test_aborts_when_already_configured(self):
        """Test that the flow aborts if the unique ID is already configured."""
        flow = self._make_flow()
        flow._force_abort_unique_id = True
        user_input = {
            CONF_NAME: "my_container",
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
        }

        with self.assertRaises(AbortFlowException) as ctx:
            await flow.async_step_user(user_input)

        self.assertEqual(ctx.exception.reason, "already_configured")


if __name__ == "__main__":
    unittest.main()

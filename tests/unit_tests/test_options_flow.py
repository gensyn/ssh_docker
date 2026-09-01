"""Tests for the SSH Docker options flow."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_docker.options_flow import SshDockerOptionsFlow, validate_and_build_options  # noqa: E402
from ssh_docker.const import DEFAULT_PORT, DEFAULT_PASSPHRASE  # noqa: E402
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
                "port": DEFAULT_PORT,
                "username": "user",
                "password": "pass",
                "passphrase": DEFAULT_PASSPHRASE,
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
            "port": 2200,
            "username": "newuser",
            "password": "newpass",
            "passphrase": "",
            "docker_command": "docker",
            "check_known_hosts": True,
            "auto_update": True,
        }
        new_options = {
            "host": "192.168.1.200",
            "port": 2200,
            "username": "newuser",
            "password": "newpass",
            "passphrase": "",
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


class TestValidateAndBuildOptions(unittest.IsolatedAsyncioTestCase):
    """Tests for validate_and_build_options service payload behavior."""

    def _make_hass(self):
        hass = MagicMock()
        hass.services.async_call = AsyncMock(return_value={"exit_status": 0})
        return hass

    def _base_input(self):
        return {
            "host": "192.168.1.200",
            "port": 2200,
            "username": "newuser",
            "key_file": "/config/id_rsa",
            "passphrase": "",
            "docker_command": "docker",
            "check_known_hosts": True,
            "auto_update": False,
            "check_for_updates": False,
        }

    async def test_omits_empty_passphrase_for_ssh_execute(self):
        """Empty passphrase is not sent to ssh_command.execute."""
        hass = self._make_hass()
        user_input = self._base_input()

        options, error_key = await validate_and_build_options(hass, user_input)

        self.assertIsNone(error_key)
        self.assertEqual(options["passphrase"], "")
        service_data = hass.services.async_call.call_args.args[2]
        self.assertNotIn("passphrase", service_data)
        self.assertEqual(service_data["port"], 2200)

    async def test_includes_non_empty_passphrase_for_ssh_execute(self):
        """Non-empty passphrase is sent to ssh_command.execute."""
        hass = self._make_hass()
        user_input = self._base_input()
        user_input["passphrase"] = "secret"

        options, error_key = await validate_and_build_options(hass, user_input)

        self.assertIsNone(error_key)
        self.assertEqual(options["passphrase"], "secret")
        service_data = hass.services.async_call.call_args.args[2]
        self.assertEqual(service_data["passphrase"], "secret")
        self.assertEqual(service_data["port"], 2200)


if __name__ == "__main__":
    unittest.main()

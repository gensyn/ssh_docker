"""Tests for the SSH Docker config flow."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_docker.config_flow import SshDockerConfigFlow, _check_service_exists  # noqa: E402
from ssh_docker.const import DOMAIN, CONF_SERVICE, SSH_CONF_OUTPUT, SSH_CONF_EXIT_STATUS  # noqa: E402
from homeassistant.config_entries import AbortFlowException  # noqa: E402
from homeassistant.const import CONF_NAME  # noqa: E402


class TestSshDockerConfigFlow(unittest.IsolatedAsyncioTestCase):
    """Test the SSH Docker config flow."""

    def _make_flow(self):
        """Create a flow instance with mocked hass."""
        flow = SshDockerConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config_entries.async_entries = MagicMock(return_value=[])
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
            CONF_NAME: "My Container",
            CONF_SERVICE: "my_container",
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

    async def test_creates_entry_with_name_and_service_in_data(self):
        """Test that a valid submission creates an entry with name and service in data."""
        flow = self._make_flow()
        user_input = {
            CONF_NAME: "My Container",
            CONF_SERVICE: "my_container",
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
        }

        with unittest.mock.patch(
            "ssh_docker.config_flow.validate_and_build_options",
            new=AsyncMock(return_value=({"host": "192.168.1.100"}, None)),
        ), unittest.mock.patch(
            "ssh_docker.config_flow._check_service_exists",
            new=AsyncMock(return_value=None),
        ):
            result = await flow.async_step_user(user_input)

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "My Container")
        self.assertEqual(result["data"][CONF_NAME], "My Container")
        self.assertEqual(result["data"][CONF_SERVICE], "my_container")

    async def test_shows_error_when_service_not_found(self):
        """Test that an error is shown when the service name is not on the host."""
        flow = self._make_flow()
        user_input = {
            CONF_NAME: "Nonexistent",
            CONF_SERVICE: "nonexistent_container",
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
        }

        with unittest.mock.patch(
            "ssh_docker.config_flow.validate_and_build_options",
            new=AsyncMock(return_value=({"host": "192.168.1.100"}, None)),
        ), unittest.mock.patch(
            "ssh_docker.config_flow._check_service_exists",
            new=AsyncMock(return_value="service_not_found"),
        ):
            result = await flow.async_step_user(user_input)

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "service_not_found")

    async def test_shows_error_when_password_key_file_missing(self):
        """Test that an error is shown when neither password nor key_file is provided."""
        flow = self._make_flow()
        user_input = {
            CONF_NAME: "My Container",
            CONF_SERVICE: "my_container",
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
            CONF_NAME: "My Container",
            CONF_SERVICE: "my_container",
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
            CONF_NAME: "My Container",
            CONF_SERVICE: "my_container",
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
        }

        with self.assertRaises(AbortFlowException) as ctx:
            await flow.async_step_user(user_input)

        self.assertEqual(ctx.exception.reason, "already_configured")

    async def test_shows_error_when_name_already_used(self):
        """Test that an error is shown when the friendly name is already in use."""
        flow = self._make_flow()
        existing_entry = MagicMock()
        existing_entry.data = {CONF_NAME: "My Container", CONF_SERVICE: "other_service"}
        flow.hass.config_entries.async_entries = MagicMock(return_value=[existing_entry])
        user_input = {
            CONF_NAME: "My Container",
            CONF_SERVICE: "new_service",
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
        }

        result = await flow.async_step_user(user_input)

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "already_configured")

    async def test_discovery_step_prefills_ssh_options(self):
        """Test that discovery flow pre-fills SSH options from the discovery data."""
        flow = self._make_flow()
        discovery_info = {
            CONF_NAME: "discovered_container",
            CONF_SERVICE: "discovered_container",
            "host": "192.168.1.100",
            "username": "admin",
            "password": "secret",
            "docker_command": "sudo docker",
        }

        result = await flow.async_step_discovery(discovery_info)

        # Should show the form with discovery data pre-filled (no user_input yet)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")
        # The stored discovery info should have the service name and all SSH options
        self.assertEqual(flow._discovery_info[CONF_SERVICE], "discovered_container")
        self.assertEqual(flow._discovery_info["host"], "192.168.1.100")
        self.assertEqual(flow._discovery_info["username"], "admin")
        self.assertEqual(flow._discovery_info["password"], "secret")
        self.assertEqual(flow._discovery_info["docker_command"], "sudo docker")

    async def test_discovery_step_aborts_when_already_configured(self):
        """Test that a discovery flow for an already-configured service is aborted."""
        flow = self._make_flow()
        flow._force_abort_unique_id = True
        discovery_info = {
            CONF_SERVICE: "existing_container",
            CONF_NAME: "existing_container",
            "host": "192.168.1.100",
        }

        with self.assertRaises(AbortFlowException) as ctx:
            await flow.async_step_discovery(discovery_info)

        self.assertEqual(ctx.exception.reason, "already_configured")


class TestCheckServiceExists(unittest.IsolatedAsyncioTestCase):
    """Tests for the _check_service_exists helper function."""

    def _make_hass(self, ssh_response: dict) -> MagicMock:
        """Build a minimal hass mock returning the given SSH response."""
        hass = MagicMock()
        hass.services.async_call = AsyncMock(return_value=ssh_response)
        return hass

    def _base_options(self) -> dict:
        return {
            "host": "192.168.1.100",
            "username": "user",
            "password": "pass",
            "check_known_hosts": True,
            "docker_command": "docker",
        }

    async def test_returns_none_when_service_found_in_json_list(self):
        """Service is in a JSON list returned by docker_services."""
        hass = self._make_hass(
            {SSH_CONF_OUTPUT: '["container_a", "container_b"]', SSH_CONF_EXIT_STATUS: 0}
        )
        result = await _check_service_exists(hass, self._base_options(), "container_a")
        self.assertIsNone(result)

    async def test_returns_error_when_service_not_in_json_list(self):
        """Service is absent from the JSON list returned by docker_services."""
        hass = self._make_hass(
            {SSH_CONF_OUTPUT: '["container_a", "container_b"]', SSH_CONF_EXIT_STATUS: 0}
        )
        result = await _check_service_exists(hass, self._base_options(), "missing_container")
        self.assertEqual(result, "service_not_found")

    async def test_returns_none_when_service_found_in_line_output(self):
        """Service is in the line-by-line fallback output of docker ps -a."""
        hass = self._make_hass(
            {SSH_CONF_OUTPUT: "container_a\ncontainer_b", SSH_CONF_EXIT_STATUS: 0}
        )
        result = await _check_service_exists(hass, self._base_options(), "container_b")
        self.assertIsNone(result)

    async def test_returns_error_when_service_not_in_line_output(self):
        """Service is missing from the line-by-line fallback output."""
        hass = self._make_hass(
            {SSH_CONF_OUTPUT: "container_a\ncontainer_b", SSH_CONF_EXIT_STATUS: 0}
        )
        result = await _check_service_exists(hass, self._base_options(), "other_container")
        self.assertEqual(result, "service_not_found")

    async def test_returns_none_when_ssh_fails(self):
        """If the SSH call raises an exception, the check is skipped (returns None)."""
        hass = MagicMock()
        hass.services.async_call = AsyncMock(side_effect=Exception("SSH error"))
        result = await _check_service_exists(hass, self._base_options(), "any_container")
        self.assertIsNone(result)

    async def test_returns_none_when_exit_status_nonzero(self):
        """A non-zero exit status means we cannot determine existence."""
        hass = self._make_hass(
            {SSH_CONF_OUTPUT: "container_a", SSH_CONF_EXIT_STATUS: 1}
        )
        result = await _check_service_exists(hass, self._base_options(), "container_a")
        self.assertIsNone(result)

    async def test_returns_none_when_output_empty(self):
        """Empty output means we cannot determine existence."""
        hass = self._make_hass({SSH_CONF_OUTPUT: "", SSH_CONF_EXIT_STATUS: 0})
        result = await _check_service_exists(hass, self._base_options(), "container_a")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

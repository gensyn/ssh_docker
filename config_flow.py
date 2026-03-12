"""Config flow for the SSH Docker integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, ConfigEntry
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_NAME
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN, CONF_KEY_FILE, CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS,
    CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND, DEFAULT_CHECK_KNOWN_HOSTS,
    SSH_COMMAND_DOMAIN, SSH_COMMAND_SERVICE_EXECUTE,
    SSH_CONF_OUTPUT, SSH_CONF_EXIT_STATUS,
    DOCKER_SERVICES_EXECUTABLE, DEFAULT_TIMEOUT,
)
from .options_flow import SshDockerOptionsFlow, validate_and_build_options

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
        vol.Optional(CONF_KEY_FILE): str,
        vol.Optional(CONF_CHECK_KNOWN_HOSTS, default=DEFAULT_CHECK_KNOWN_HOSTS): bool,
        vol.Optional(CONF_KNOWN_HOSTS): str,
        vol.Optional(CONF_DOCKER_COMMAND, default=DEFAULT_DOCKER_COMMAND): str,
    }
)


async def _check_service_exists(
        hass: HomeAssistant, options: dict[str, Any], name: str
) -> str | None:
    """Check whether a service name is present on the remote host.

    Runs the same discovery logic used by the integration: prefers the
    ``docker_services`` executable and falls back to ``docker ps -a``.

    Returns ``None`` when the service is found *or* when the check cannot be
    performed (SSH unreachable, empty output, etc.).  Returns
    ``"service_not_found"`` only when a non-empty list was retrieved and the
    requested name is absent from it.
    """
    docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
    discover_cmd = (
        f"if command -v {DOCKER_SERVICES_EXECUTABLE} >/dev/null 2>&1; then"
        f" {DOCKER_SERVICES_EXECUTABLE};"
        f" elif test -f /usr/bin/{DOCKER_SERVICES_EXECUTABLE}; then"
        f" /usr/bin/{DOCKER_SERVICES_EXECUTABLE};"
        f" else {docker_cmd} ps -a --format '{{{{.Names}}}}'; fi"
    )

    service_data: dict[str, Any] = {
        CONF_HOST: options.get(CONF_HOST, ""),
        CONF_USERNAME: options.get(CONF_USERNAME, ""),
        "check_known_hosts": options.get(CONF_CHECK_KNOWN_HOSTS, DEFAULT_CHECK_KNOWN_HOSTS),
        "command": discover_cmd,
        "timeout": DEFAULT_TIMEOUT,
    }
    if options.get(CONF_PASSWORD):
        service_data[CONF_PASSWORD] = options[CONF_PASSWORD]
    if options.get(CONF_KEY_FILE):
        service_data["key_file"] = options[CONF_KEY_FILE]
    if options.get(CONF_KNOWN_HOSTS):
        service_data["known_hosts"] = options[CONF_KNOWN_HOSTS]

    try:
        response = await hass.services.async_call(
            SSH_COMMAND_DOMAIN,
            SSH_COMMAND_SERVICE_EXECUTE,
            service_data,
            blocking=True,
            return_response=True,
        )
    except Exception:  # pylint: disable=broad-except
        _LOGGER.debug(
            "Service existence check for %s on %s failed, skipping check",
            name,
            options.get(CONF_HOST, "<unknown>"),
        )
        return None

    output = ((response or {}).get(SSH_CONF_OUTPUT, "") or "").strip()
    exit_status = (response or {}).get(SSH_CONF_EXIT_STATUS, 1)

    if exit_status != 0 or not output:
        _LOGGER.debug(
            "Service listing on %s returned no usable output, skipping existence check",
            options.get(CONF_HOST, "<unknown>"),
        )
        return None

    try:
        parsed = json.loads(output)
        service_names = [str(s) for s in parsed if s] if isinstance(parsed, list) else []
    except (json.JSONDecodeError, ValueError):
        service_names = [line.strip() for line in output.splitlines() if line.strip()]

    if not service_names:
        _LOGGER.debug(
            "Service listing on %s returned an empty list, skipping existence check",
            options.get(CONF_HOST, "<unknown>"),
        )
        return None

    if name in service_names:
        _LOGGER.debug("Service %s confirmed on %s", name, options.get(CONF_HOST, "<unknown>"))
        return None

    _LOGGER.warning(
        "Service %s not found on %s. Available services: %s",
        name,
        options.get(CONF_HOST, "<unknown>"),
        service_names,
    )
    return "service_not_found"


def _build_user_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the user-step schema, optionally pre-filled with *defaults*."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Optional(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Optional(CONF_KEY_FILE, default=defaults.get(CONF_KEY_FILE, "")): str,
            vol.Optional(
                CONF_CHECK_KNOWN_HOSTS,
                default=defaults.get(CONF_CHECK_KNOWN_HOSTS, DEFAULT_CHECK_KNOWN_HOSTS),
            ): bool,
            vol.Optional(CONF_KNOWN_HOSTS, default=defaults.get(CONF_KNOWN_HOSTS, "")): str,
            vol.Optional(
                CONF_DOCKER_COMMAND,
                default=defaults.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND),
            ): str,
        }
    )


class SshDockerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SSH Docker."""

    VERSION = 1

    async def async_step_user(
            self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        discovery = getattr(self, "_discovery_info", {})

        if user_input is not None:
            name = user_input[CONF_NAME]
            _LOGGER.debug(
                "Config flow user step: validating entry for container %s on %s",
                name,
                user_input.get(CONF_HOST, "<unknown>"),
            )
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}_{name}")
            self._abort_if_unique_id_configured()

            options, error_key = await validate_and_build_options(self.hass, user_input)
            if error_key:
                _LOGGER.debug(
                    "Config flow validation failed for container %s: %s", name, error_key
                )
                errors["base"] = error_key
            else:
                error_key = await _check_service_exists(self.hass, options, name)
                if error_key:
                    _LOGGER.debug(
                        "Service existence check failed for container %s: %s", name, error_key
                    )
                    errors["base"] = error_key
                else:
                    _LOGGER.info(
                        "Config entry created for container %s on %s",
                        name,
                        user_input[CONF_HOST],
                    )
                    return self.async_create_entry(
                        title=name,
                        data={CONF_NAME: name},
                        options=options,
                    )

        schema = _build_user_schema(discovery) if discovery else STEP_USER_DATA_SCHEMA
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_discovery(
            self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle a discovered docker service."""
        name = discovery_info.get(CONF_NAME, "")
        host = discovery_info.get(CONF_HOST, "")
        _LOGGER.debug("Discovery flow: container %s found on %s", name, host)

        await self.async_set_unique_id(f"{host}_{name}")
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {CONF_NAME: name, CONF_HOST: host}
        self._discovery_info = discovery_info  # pylint: disable=attribute-defined-outside-init
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(
            config_entry: ConfigEntry,  # pylint: disable=unused-argument
    ) -> SshDockerOptionsFlow:
        """Create the options flow."""
        return SshDockerOptionsFlow()

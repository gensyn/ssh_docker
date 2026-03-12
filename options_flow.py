"""Options flow for the SSH Docker integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import OptionsFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError, HomeAssistantError

from .const import (
    CONF_KEY_FILE, CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS,
    CONF_DOCKER_COMMAND, CONF_AUTO_UPDATE, DEFAULT_DOCKER_COMMAND,
    DEFAULT_CHECK_KNOWN_HOSTS, DEFAULT_AUTO_UPDATE,
    SSH_COMMAND_DOMAIN, SSH_COMMAND_SERVICE_EXECUTE, SSH_CONF_EXIT_STATUS,
)

_LOGGER = logging.getLogger(__name__)


async def validate_and_build_options(
        hass: HomeAssistant, user_input: dict[str, Any]
) -> tuple[dict[str, Any], str | None]:
    """Validate SSH connection and build options dict. Returns (options, error_key)."""
    has_password = bool(user_input.get(CONF_PASSWORD))
    has_key_file = bool(user_input.get(CONF_KEY_FILE))

    if not has_password and not has_key_file:
        _LOGGER.debug(
            "Validation failed for host %s: neither password nor key_file provided",
            user_input.get(CONF_HOST, "<unknown>"),
        )
        return {}, "password_or_key_file_required"

    docker_cmd = user_input.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)

    service_data: dict[str, Any] = {
        CONF_HOST: user_input[CONF_HOST],
        CONF_USERNAME: user_input[CONF_USERNAME],
        "check_known_hosts": user_input.get(CONF_CHECK_KNOWN_HOSTS, DEFAULT_CHECK_KNOWN_HOSTS),
        "command": f"{docker_cmd} ps -q",
    }
    if has_password:
        service_data[CONF_PASSWORD] = user_input[CONF_PASSWORD]
    if has_key_file:
        service_data["key_file"] = user_input[CONF_KEY_FILE]
    if user_input.get(CONF_KNOWN_HOSTS):
        service_data["known_hosts"] = user_input[CONF_KNOWN_HOSTS]

    _LOGGER.debug(
        "Validating SSH connection to %s as %s",
        user_input[CONF_HOST],
        user_input[CONF_USERNAME],
    )
    try:
        response = await hass.services.async_call(
            SSH_COMMAND_DOMAIN,
            SSH_COMMAND_SERVICE_EXECUTE,
            service_data,
            blocking=True,
            return_response=True,
        )
        exit_status = response.get(SSH_CONF_EXIT_STATUS, 1) if response else 1
        if exit_status != 0:
            _LOGGER.warning(
                "SSH validation for host %s: docker command failed (exit status %d)",
                user_input[CONF_HOST],
                exit_status,
            )
            return {}, "docker_command_failed"
    except ServiceValidationError as exc:
        translation_key = exc.translation_key if hasattr(exc, "translation_key") else "cannot_connect"
        _LOGGER.warning(
            "SSH validation for host %s raised ServiceValidationError: %s",
            user_input[CONF_HOST],
            exc,
        )
        return {}, translation_key
    except HomeAssistantError as exc:
        _LOGGER.warning(
            "SSH validation for host %s raised HomeAssistantError: %s",
            user_input[CONF_HOST],
            exc,
        )
        return {}, "cannot_connect"
    except Exception as exc:  # pylint: disable=broad-except
        _LOGGER.warning(
            "SSH validation for host %s raised an unexpected exception: %s",
            user_input[CONF_HOST],
            exc,
        )
        return {}, "cannot_connect"

    _LOGGER.debug("SSH validation successful for host %s", user_input[CONF_HOST])
    options: dict[str, Any] = {
        CONF_HOST: user_input[CONF_HOST],
        CONF_USERNAME: user_input[CONF_USERNAME],
        CONF_CHECK_KNOWN_HOSTS: user_input.get(CONF_CHECK_KNOWN_HOSTS, DEFAULT_CHECK_KNOWN_HOSTS),
        CONF_DOCKER_COMMAND: docker_cmd,
        CONF_AUTO_UPDATE: user_input.get(CONF_AUTO_UPDATE, DEFAULT_AUTO_UPDATE),
    }
    if has_password:
        options[CONF_PASSWORD] = user_input[CONF_PASSWORD]
    if has_key_file:
        options[CONF_KEY_FILE] = user_input[CONF_KEY_FILE]
    if user_input.get(CONF_KNOWN_HOSTS):
        options[CONF_KNOWN_HOSTS] = user_input[CONF_KNOWN_HOSTS]

    return options, None


STEP_OPTIONS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
        vol.Optional(CONF_KEY_FILE): str,
        vol.Optional(CONF_CHECK_KNOWN_HOSTS, default=DEFAULT_CHECK_KNOWN_HOSTS): bool,
        vol.Optional(CONF_KNOWN_HOSTS): str,
        vol.Optional(CONF_DOCKER_COMMAND, default=DEFAULT_DOCKER_COMMAND): str,
        vol.Optional(CONF_AUTO_UPDATE, default=DEFAULT_AUTO_UPDATE): bool,
    }
)


class SshDockerOptionsFlow(OptionsFlow):
    """Handle options for SSH Docker."""

    async def async_step_init(
            self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug(
                "Options flow: validating updated settings for %s",
                user_input.get(CONF_HOST, "<unknown>"),
            )
            options, error_key = await validate_and_build_options(self.hass, user_input)
            if error_key:
                _LOGGER.debug("Options flow validation failed: %s", error_key)
                errors["base"] = error_key
            else:
                _LOGGER.info("Options updated for host %s", user_input.get(CONF_HOST))
                return self.async_create_entry(data=options)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): str,
                vol.Required(CONF_USERNAME, default=current.get(CONF_USERNAME, "")): str,
                vol.Optional(CONF_PASSWORD, default=current.get(CONF_PASSWORD, "")): str,
                vol.Optional(CONF_KEY_FILE, default=current.get(CONF_KEY_FILE, "")): str,
                vol.Optional(
                    CONF_CHECK_KNOWN_HOSTS,
                    default=current.get(CONF_CHECK_KNOWN_HOSTS, DEFAULT_CHECK_KNOWN_HOSTS),
                ): bool,
                vol.Optional(CONF_KNOWN_HOSTS, default=current.get(CONF_KNOWN_HOSTS, "")): str,
                vol.Optional(
                    CONF_DOCKER_COMMAND,
                    default=current.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND),
                ): str,
                vol.Optional(
                    CONF_AUTO_UPDATE,
                    default=current.get(CONF_AUTO_UPDATE, DEFAULT_AUTO_UPDATE),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )

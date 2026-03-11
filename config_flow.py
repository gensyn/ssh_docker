"""Config flow for the SSH Docker integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, ConfigEntry
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_NAME
from homeassistant.core import callback

from .const import (
    DOMAIN, CONF_KEY_FILE, CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS,
    CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND, DEFAULT_CHECK_KNOWN_HOSTS,
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


class SshDockerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SSH Docker."""

    VERSION = 1

    async def async_step_user(
            self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}_{name}")
            self._abort_if_unique_id_configured()

            options, error_key = await validate_and_build_options(self.hass, user_input)
            if error_key:
                errors["base"] = error_key
            else:
                return self.async_create_entry(
                    title=name,
                    data={CONF_NAME: name},
                    options=options,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_discovery(
            self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle a discovered docker service."""
        name = discovery_info.get(CONF_NAME, "")
        host = discovery_info.get(CONF_HOST, "")

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

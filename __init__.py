"""The SSH Docker integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, SOURCE_DISCOVERY
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError, HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, CONF_KEY_FILE, CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS,
    CONF_DOCKER_COMMAND, CONF_AUTO_UPDATE, CONF_SERVICE,
    SSH_COMMAND_DOMAIN, SSH_COMMAND_SERVICE_EXECUTE,
    SSH_CONF_OUTPUT, SSH_CONF_EXIT_STATUS,
    SERVICE_CREATE, SERVICE_RESTART, SERVICE_STOP, SERVICE_REMOVE,
    DEFAULT_DOCKER_COMMAND, DEFAULT_CHECK_KNOWN_HOSTS, DEFAULT_TIMEOUT,
    DOCKER_SERVICES_EXECUTABLE, DOCKER_CREATE_EXECUTABLE, DOCKER_CREATE_TIMEOUT,
)
from .frontend import SshDockerPanelRegistration
from .sensor import DockerContainerSensor

_PLATFORMS: list[Platform] = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)  # pylint: disable=invalid-name

SERVICE_ENTITY_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): str,
    }
)


async def _ssh_run(
    hass: HomeAssistant,
    options: dict[str, Any],
    command: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[str, int]:
    """Execute a command via ssh_command service. Returns (stdout, exit_status)."""
    _LOGGER.debug(
        "Running SSH command on %s: %s", options.get(CONF_HOST, "<unknown>"), command
    )
    service_data: dict[str, Any] = {
        CONF_HOST: options[CONF_HOST],
        CONF_USERNAME: options[CONF_USERNAME],
        "check_known_hosts": options.get(CONF_CHECK_KNOWN_HOSTS, DEFAULT_CHECK_KNOWN_HOSTS),
        "command": command,
        "timeout": timeout,
    }
    if options.get(CONF_PASSWORD):
        service_data[CONF_PASSWORD] = options[CONF_PASSWORD]
    if options.get(CONF_KEY_FILE):
        service_data["key_file"] = options[CONF_KEY_FILE]
    if options.get(CONF_KNOWN_HOSTS):
        service_data["known_hosts"] = options[CONF_KNOWN_HOSTS]

    response = await hass.services.async_call(
        SSH_COMMAND_DOMAIN,
        SSH_COMMAND_SERVICE_EXECUTE,
        service_data,
        blocking=True,
        return_response=True,
    )
    output = (response or {}).get(SSH_CONF_OUTPUT, "").strip()
    exit_status = (response or {}).get(SSH_CONF_EXIT_STATUS, 1)
    # asyncssh returns None for signal-based terminations; normalize to -1
    if exit_status is None:
        exit_status = -1
    _LOGGER.debug(
        "SSH command on %s exited with status %s", options.get(CONF_HOST, "<unknown>"), exit_status
    )
    return output, exit_status


def _get_entry_for_entity(hass: HomeAssistant, entity_id: str) -> ConfigEntry:
    """Return the config entry associated with the given entity_id."""
    reg = entity_registry.async_get(hass)
    entry_obj = reg.async_get(entity_id)  # pylint: disable=assignment-from-none
    if entry_obj is None:
        _LOGGER.error("Entity %s not found in entity registry", entity_id)
        raise ServiceValidationError(
            f"Entity {entity_id} not found in registry",
            translation_domain=DOMAIN,
            translation_key="entity_not_found",
        )
    config_entry = hass.config_entries.async_get_entry(entry_obj.config_entry_id)
    if config_entry is None:
        _LOGGER.error(
            "Config entry for entity %s (entry id: %s) not found",
            entity_id,
            entry_obj.config_entry_id,
        )
        raise ServiceValidationError(
            f"Config entry for {entity_id} not found",
            translation_domain=DOMAIN,
            translation_key="entity_not_found",
        )
    return config_entry


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the SSH Docker integration and register services."""
    _LOGGER.debug("Setting up SSH Docker integration")
    hass.data.setdefault(DOMAIN, {})
    panel = SshDockerPanelRegistration(hass)
    await panel.async_register()

    async def async_create(service_call: ServiceCall) -> None:
        """Create a docker container using the docker_create executable."""
        entity_id = service_call.data["entity_id"]
        _LOGGER.debug("Service 'create' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        options = entry.options
        name = entry.data.get(CONF_SERVICE, entry.data[CONF_NAME])
        sensor = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if sensor:
            sensor.set_transitional_state("creating")

        check_cmd = (
            f"command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1 && echo found"
            f" || (test -f /usr/bin/{DOCKER_CREATE_EXECUTABLE} && echo found || echo not_found)"
        )
        try:
            output, _ = await _ssh_run(hass, options, check_cmd)
            if output.strip() != "found":
                _LOGGER.error(
                    "Service 'create' for container %s: %s not found on host",
                    name,
                    DOCKER_CREATE_EXECUTABLE,
                )
                raise ServiceValidationError(
                    f"{DOCKER_CREATE_EXECUTABLE} not found on host",
                    translation_domain=DOMAIN,
                    translation_key="docker_create_not_found",
                )

            # Use if/then/else to run docker_create exactly once and preserve its exit code.
            create_cmd = (
                f"if command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1;"
                f" then {DOCKER_CREATE_EXECUTABLE} {name};"
                f" else /usr/bin/{DOCKER_CREATE_EXECUTABLE} {name}; fi"
            )
            _, exit_status = await _ssh_run(
                hass, options, create_cmd, timeout=DOCKER_CREATE_TIMEOUT
            )
            if exit_status != 0:
                # The docker_create script may exit non-zero for recoverable reasons
                # (e.g. cleanup commands that fail when the container does not yet exist)
                # while still successfully creating the container.  Log a warning and let
                # the follow-up sensor refresh reveal the real container state.
                _LOGGER.warning(
                    "Service 'create': %s exited with status %s for container %s; "
                    "the container may still have been created — check the sensor state",
                    DOCKER_CREATE_EXECUTABLE,
                    exit_status,
                    name,
                )
            else:
                _LOGGER.info("Service 'create': successfully created container %s", name)
        finally:
            if sensor:
                sensor.async_schedule_update_ha_state(force_refresh=True)

    async def async_restart(service_call: ServiceCall) -> None:
        """Restart a docker container."""
        entity_id = service_call.data["entity_id"]
        _LOGGER.debug("Service 'restart' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        options = entry.options
        name = entry.data.get(CONF_SERVICE, entry.data[CONF_NAME])
        docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
        sensor = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if sensor:
            sensor.set_transitional_state("restarting")

        try:
            _, exit_status = await _ssh_run(hass, options, f"{docker_cmd} restart {name}")
            if exit_status != 0:
                _LOGGER.error(
                    "Service 'restart' failed for container %s (exit status %d)", name, exit_status
                )
                raise ServiceValidationError(
                    f"Failed to restart container {name}",
                    translation_domain=DOMAIN,
                    translation_key="docker_command_failed",
                )
            _LOGGER.info("Service 'restart': successfully restarted container %s", name)
        finally:
            if sensor:
                sensor.async_schedule_update_ha_state(force_refresh=True)

    async def async_stop(service_call: ServiceCall) -> None:
        """Stop a docker container."""
        entity_id = service_call.data["entity_id"]
        _LOGGER.debug("Service 'stop' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        options = entry.options
        name = entry.data.get(CONF_SERVICE, entry.data[CONF_NAME])
        docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
        sensor = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if sensor:
            sensor.set_transitional_state("stopping")

        try:
            _, exit_status = await _ssh_run(hass, options, f"{docker_cmd} stop {name}")
            if exit_status != 0:
                _LOGGER.error(
                    "Service 'stop' failed for container %s (exit status %d)", name, exit_status
                )
                raise ServiceValidationError(
                    f"Failed to stop container {name}",
                    translation_domain=DOMAIN,
                    translation_key="docker_command_failed",
                )
            _LOGGER.info("Service 'stop': successfully stopped container %s", name)
        finally:
            if sensor:
                sensor.async_schedule_update_ha_state(force_refresh=True)

    async def async_remove(service_call: ServiceCall) -> None:
        """Stop and remove a docker container."""
        entity_id = service_call.data["entity_id"]
        _LOGGER.debug("Service 'remove' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        options = entry.options
        name = entry.data.get(CONF_SERVICE, entry.data[CONF_NAME])
        docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
        sensor = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if sensor:
            sensor.set_transitional_state("removing")

        try:
            _, exit_status = await _ssh_run(
                hass, options, f"{docker_cmd} stop {name}; {docker_cmd} rm {name}"
            )
            if exit_status != 0:
                _LOGGER.error(
                    "Service 'remove' failed for container %s (exit status %d)", name, exit_status
                )
                raise ServiceValidationError(
                    f"Failed to remove container {name}",
                    translation_domain=DOMAIN,
                    translation_key="docker_command_failed",
                )
            _LOGGER.info("Service 'remove': successfully removed container %s", name)
        finally:
            if sensor:
                sensor.async_schedule_update_ha_state(force_refresh=True)

    hass.services.async_register(DOMAIN, SERVICE_CREATE, async_create, schema=SERVICE_ENTITY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESTART, async_restart, schema=SERVICE_ENTITY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP, async_stop, schema=SERVICE_ENTITY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE, async_remove, schema=SERVICE_ENTITY_SCHEMA)

    _LOGGER.debug("SSH Docker integration setup complete")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SSH Docker from a config entry."""
    _LOGGER.debug("Setting up config entry for container %s", entry.data.get(CONF_NAME))
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    hass.async_create_task(_discover_services(hass, entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading config entry for container %s", entry.data.get(CONF_NAME))
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)


async def _discover_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Discover additional docker services on the host and suggest them."""
    options = entry.options
    host = options[CONF_HOST]
    docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
    _LOGGER.debug("Starting docker service discovery on %s", host)

    discover_cmd = (
        f"if command -v {DOCKER_SERVICES_EXECUTABLE} >/dev/null 2>&1; then"
        f" {DOCKER_SERVICES_EXECUTABLE};"
        f" elif test -f /usr/bin/{DOCKER_SERVICES_EXECUTABLE}; then"
        f" /usr/bin/{DOCKER_SERVICES_EXECUTABLE};"
        f" else {docker_cmd} ps -a --format '{{{{.Names}}}}'; fi"
    )

    try:
        output, exit_status = await _ssh_run(hass, options, discover_cmd)
    except (ServiceValidationError, HomeAssistantError, Exception) as err:  # pylint: disable=broad-except
        _LOGGER.warning("Service discovery on %s failed: %s", host, err)
        return

    if exit_status != 0:
        _LOGGER.warning(
            "Service discovery on %s returned non-zero exit status %d", host, exit_status
        )
        return

    if not output:
        _LOGGER.debug("Service discovery on %s returned no output", host)
        return

    service_names: list[str] = []
    try:
        parsed = json.loads(output)
        if isinstance(parsed, list):
            service_names = [str(s) for s in parsed if s]
        _LOGGER.debug(
            "Service discovery on %s: parsed %d service(s) from JSON", host, len(service_names)
        )
    except (json.JSONDecodeError, ValueError):
        _LOGGER.debug(
            "Service discovery on %s: JSON parse failed, falling back to space/comma/newline-separated parsing",
            host,
        )
        service_names = [s for s in output.replace(",", " ").split() if s]

    configured_services = {
        e.data.get(CONF_SERVICE, e.data[CONF_NAME])
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.options.get(CONF_HOST) == host
    }

    new_count = 0
    for service_name in service_names:
        if service_name in configured_services:
            continue
        _LOGGER.debug("Discovered docker service: %s on %s", service_name, host)
        # Build discovery data with full SSH options so the config flow can
        # pre-fill the form for the user.
        discovery_data: dict[str, Any] = {
            CONF_SERVICE: service_name,
            CONF_NAME: service_name[0].upper() + service_name[1:] if service_name else service_name,
            CONF_HOST: host,
            CONF_USERNAME: options.get(CONF_USERNAME, ""),
            CONF_DOCKER_COMMAND: options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND),
            CONF_CHECK_KNOWN_HOSTS: options.get(CONF_CHECK_KNOWN_HOSTS, DEFAULT_CHECK_KNOWN_HOSTS),
        }
        if options.get(CONF_PASSWORD):
            discovery_data[CONF_PASSWORD] = options[CONF_PASSWORD]
        if options.get(CONF_KEY_FILE):
            discovery_data[CONF_KEY_FILE] = options[CONF_KEY_FILE]
        if options.get(CONF_KNOWN_HOSTS):
            discovery_data[CONF_KNOWN_HOSTS] = options[CONF_KNOWN_HOSTS]

        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_DISCOVERY},
                data=discovery_data,
            )
        )
        new_count += 1

    _LOGGER.debug(
        "Service discovery on %s complete: %d new service(s) discovered", host, new_count
    )
"""The SSH Docker integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, SOURCE_DISCOVERY
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, ServiceResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, CONF_KEY_FILE, CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS,
    CONF_DOCKER_COMMAND, CONF_AUTO_UPDATE, CONF_CHECK_FOR_UPDATES, CONF_SERVICE,
    SERVICE_CREATE, SERVICE_RESTART, SERVICE_STOP, SERVICE_REMOVE, SERVICE_REFRESH,
    SERVICE_GET_LOGS, SERVICE_EXECUTE_COMMAND,
    DEFAULT_DOCKER_COMMAND, DEFAULT_CHECK_KNOWN_HOSTS, DEFAULT_TIMEOUT,
    DEFAULT_AUTO_UPDATE, DEFAULT_CHECK_FOR_UPDATES,
    DOCKER_SERVICES_EXECUTABLE,
)
from .coordinator import SshDockerCoordinator, _ssh_run, _check_service_available
from .frontend import SshDockerPanelRegistration

_PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.UPDATE]
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)  # pylint: disable=invalid-name

SERVICE_ENTITY_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): str,
    }
)

SERVICE_EXECUTE_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): str,
        vol.Required("command"): str,
        vol.Optional("timeout"): vol.All(int, vol.Range(min=1)),
    }
)


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


def _get_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> SshDockerCoordinator:
    """Return the coordinator for *entry*, raising ServiceValidationError if absent."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        raise ServiceValidationError(
            f"Coordinator for entry {entry.entry_id} not found",
            translation_domain=DOMAIN,
            translation_key="entity_not_found",
        )
    return coordinator


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
        coordinator = _get_coordinator(hass, entry)
        coordinator.set_pending_state("creating")
        try:
            await coordinator.create()
        finally:
            await coordinator.async_request_refresh()

    async def async_restart(service_call: ServiceCall) -> None:
        """Restart a docker container."""
        entity_id = service_call.data["entity_id"]
        _LOGGER.debug("Service 'restart' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        coordinator = _get_coordinator(hass, entry)
        coordinator.set_pending_state("starting")
        try:
            await coordinator.restart()
        finally:
            await coordinator.async_request_refresh()

    async def async_stop(service_call: ServiceCall) -> None:
        """Stop a docker container."""
        entity_id = service_call.data["entity_id"]
        _LOGGER.debug("Service 'stop' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        coordinator = _get_coordinator(hass, entry)
        coordinator.set_pending_state("stopping")
        try:
            await coordinator.stop()
        finally:
            await coordinator.async_request_refresh()

    async def async_remove(service_call: ServiceCall) -> None:
        """Stop and remove a docker container."""
        entity_id = service_call.data["entity_id"]
        _LOGGER.debug("Service 'remove' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        coordinator = _get_coordinator(hass, entry)
        coordinator.set_pending_state("removing")
        try:
            await coordinator.remove()
        finally:
            await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_CREATE, async_create, schema=SERVICE_ENTITY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESTART, async_restart, schema=SERVICE_ENTITY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP, async_stop, schema=SERVICE_ENTITY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE, async_remove, schema=SERVICE_ENTITY_SCHEMA)

    async def async_refresh(service_call: ServiceCall) -> None:
        """Refresh a docker container sensor state."""
        entity_id = service_call.data["entity_id"]
        _LOGGER.debug("Service 'refresh' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        coordinator = _get_coordinator(hass, entry)
        coordinator.set_pending_state("refreshing")
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, async_refresh, schema=SERVICE_ENTITY_SCHEMA)

    async def async_get_logs(service_call: ServiceCall) -> ServiceResponse:
        """Return recent logs for a docker container."""
        entity_id = service_call.data["entity_id"]
        _LOGGER.debug("Service 'get_logs' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        coordinator = _get_coordinator(hass, entry)
        logs = await coordinator.get_logs()
        return {"logs": logs}

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_LOGS,
        async_get_logs,
        schema=SERVICE_ENTITY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def async_execute_command(service_call: ServiceCall) -> ServiceResponse:
        """Execute an arbitrary command inside the docker container."""
        entity_id = service_call.data["entity_id"]
        command = service_call.data["command"]
        timeout = service_call.data.get("timeout", DEFAULT_TIMEOUT)
        _LOGGER.debug("Service 'execute_command' called for entity %s", entity_id)
        entry = _get_entry_for_entity(hass, entity_id)
        coordinator = _get_coordinator(hass, entry)
        output, exit_status = await coordinator.execute_command(command, timeout=timeout)
        return {"output": output, "exit_status": exit_status}

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_COMMAND,
        async_execute_command,
        schema=SERVICE_EXECUTE_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    _LOGGER.debug("SSH Docker integration setup complete")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SSH Docker from a config entry."""
    _LOGGER.debug("Setting up config entry for container %s", entry.data.get(CONF_NAME))

    # Fail setup if docker_services is present on the host and no longer lists
    # this service in its output.
    if not await _check_service_available(hass, entry):
        service = entry.data.get(CONF_SERVICE, entry.data.get(CONF_NAME, ""))
        _LOGGER.error(
            "Service %s is no longer listed by %s on %s; refusing to set up entry",
            service,
            DOCKER_SERVICES_EXECUTABLE,
            entry.options.get(CONF_HOST, "<unknown>"),
        )
        return False

    # Create (and store) the coordinator before platforms are loaded so that
    # both sensor and update platforms can retrieve it via hass.data.
    coordinator = SshDockerCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
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
    except Exception as err:  # pylint: disable=broad-except
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
            CONF_CHECK_FOR_UPDATES: options.get(CONF_CHECK_FOR_UPDATES, DEFAULT_CHECK_FOR_UPDATES),
            CONF_AUTO_UPDATE: options.get(CONF_AUTO_UPDATE, DEFAULT_AUTO_UPDATE),
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
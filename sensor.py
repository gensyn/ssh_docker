"""Platform for sensor integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    DOMAIN, CONF_SERVICE, CONF_KEY_FILE, CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS,
    CONF_DOCKER_COMMAND, CONF_AUTO_UPDATE, CONF_UPDATE_AVAILABLE,
    CONF_CREATED, CONF_IMAGE, SSH_COMMAND_DOMAIN, SSH_COMMAND_SERVICE_EXECUTE,
    SSH_CONF_OUTPUT, SSH_CONF_EXIT_STATUS, DEFAULT_DOCKER_COMMAND,
    DEFAULT_CHECK_KNOWN_HOSTS, DEFAULT_TIMEOUT, DOCKER_CREATE_EXECUTABLE,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=24)

STATE_UNAVAILABLE = "unavailable"


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SSH Docker sensor platform from a config entry."""
    sensor = DockerContainerSensor(entry, hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = sensor
    async_add_entities([sensor], update_before_add=True)


async def _ssh_run(hass: HomeAssistant, options: dict[str, Any], command: str) -> tuple[str, int]:
    """Run a command via the ssh_command service. Returns (stdout, exit_status)."""
    service_data: dict[str, Any] = {
        CONF_HOST: options[CONF_HOST],
        CONF_USERNAME: options[CONF_USERNAME],
        "check_known_hosts": options.get(CONF_CHECK_KNOWN_HOSTS, DEFAULT_CHECK_KNOWN_HOSTS),
        "command": command,
        "timeout": DEFAULT_TIMEOUT,
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
    return output, exit_status


class DockerContainerSensor(SensorEntity):
    """Sensor representing a Docker container on a remote host."""

    _attr_has_entity_name = True
    _attr_translation_key = "state"
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, hass: HomeAssistant) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.entry = entry
        self.hass = hass
        self._name = entry.data[CONF_NAME]
        # service is the container name used in docker commands; falls back to
        # name for backwards compatibility with entries created before the split.
        self._service = entry.data.get(CONF_SERVICE, self._name)
        self._attr_unique_id = f"{entry.entry_id}_state"
        self.entity_id = generate_entity_id(
            "sensor.ssh_docker_{}", slugify(self._name), hass=hass
        )
        self._attr_native_value = STATE_UNAVAILABLE
        self._attr_extra_state_attributes: dict[str, Any] = {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="SSH Docker",
            model="Docker Container",
            name=self._name,
        )

    async def async_update(self) -> None:
        """Fetch the latest state from the remote docker host."""
        options = self.entry.options
        docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
        service = self._service
        host = options.get(CONF_HOST, "")
        _LOGGER.debug("Updating sensor for container %s", service)

        info_cmd = (
            f"{docker_cmd} inspect {service}"
            f" --format '{{{{.State.Status}}}};{{{{.Created}}}};{{{{.Config.Image}}}};{{{{.Image}}}}'"
        )
        try:
            output, exit_status = await _ssh_run(self.hass, options, info_cmd)
        except (ServiceValidationError, HomeAssistantError, Exception) as err:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to inspect container %s: %s", service, err)
            self._attr_native_value = STATE_UNAVAILABLE
            self._attr_extra_state_attributes = {"host": host, "docker_create_available": False}
            return

        if exit_status != 0 or not output:
            _LOGGER.debug(
                "Container %s not found or docker inspect returned no output (exit status %d)",
                service,
                exit_status,
            )
            docker_create_available = await self._check_docker_create_available(options)
            self._attr_native_value = STATE_UNAVAILABLE
            self._attr_extra_state_attributes = {
                "host": host,
                "docker_create_available": docker_create_available,
            }
            return

        parts = output.split(";", 3)
        if len(parts) < 4:
            _LOGGER.warning(
                "Unexpected docker inspect output format for container %s: %r", service, output
            )
            docker_create_available = await self._check_docker_create_available(options)
            self._attr_native_value = STATE_UNAVAILABLE
            self._attr_extra_state_attributes = {
                "host": host,
                "docker_create_available": docker_create_available,
            }
            return

        container_state, created, image_name, old_image_id = parts

        update_available = False
        pull_cmd = (
            f"{docker_cmd} pull {image_name} > /dev/null 2>&1;"
            f" {docker_cmd} image inspect {image_name} --format '{{{{.Id}}}}'"
        )
        try:
            new_image_id, _ = await _ssh_run(self.hass, options, pull_cmd)
            update_available = bool(new_image_id) and new_image_id != old_image_id.strip()
            if update_available:
                _LOGGER.info(
                    "Update available for container %s: image %s has a newer version",
                    service,
                    image_name,
                )
        except (ServiceValidationError, HomeAssistantError, Exception) as err:  # pylint: disable=broad-except
            _LOGGER.debug("Could not check for image updates for %s: %s", service, err)

        # Check docker_create availability (for the panel Create button).
        docker_create_available = await self._check_docker_create_available(options)

        _LOGGER.debug(
            "Container %s state: %s, update_available: %s", service, container_state, update_available
        )
        self._attr_native_value = container_state
        self._attr_extra_state_attributes = {
            CONF_CREATED: created,
            CONF_IMAGE: image_name,
            CONF_UPDATE_AVAILABLE: update_available,
            "host": host,
            "docker_create_available": docker_create_available,
        }

        if update_available and options.get(CONF_AUTO_UPDATE, False):
            await self._auto_recreate(options, service, docker_create_available)

    def set_transitional_state(self, state: str) -> None:
        """Set a transitional state and write it to HA immediately."""
        _LOGGER.debug("Container %s entering transitional state: %s", self._name, state)
        self._attr_native_value = state
        self.async_write_ha_state()

    async def _check_docker_create_available(self, options: dict[str, Any]) -> bool:
        """Return True if the docker_create executable is present on the remote host."""
        check_cmd = (
            f"command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1 && echo found"
            f" || (test -f /usr/bin/{DOCKER_CREATE_EXECUTABLE} && echo found || echo not_found)"
        )
        try:
            output, _ = await _ssh_run(self.hass, options, check_cmd)
            return output.strip() == "found"
        except (ServiceValidationError, HomeAssistantError, Exception) as err:  # pylint: disable=broad-except
            _LOGGER.debug("Could not check for docker_create on host: %s", err)
            return False

    async def _auto_recreate(
            self, options: dict[str, Any], name: str, docker_create_available: bool = False
    ) -> None:
        """Recreate the container using docker_create if available."""
        if not docker_create_available:
            _LOGGER.warning(
                "Auto-update: docker_create not found on host for container %s", name
            )
            return
        create_cmd = (
            f"command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1"
            f" && {DOCKER_CREATE_EXECUTABLE} {name}"
            f" || /usr/bin/{DOCKER_CREATE_EXECUTABLE} {name}"
        )
        try:
            _, exit_status = await _ssh_run(self.hass, options, create_cmd)
            if exit_status != 0:
                _LOGGER.warning("Auto-update: docker_create failed for %s", name)
            else:
                _LOGGER.info("Auto-update: recreated container %s", name)
        except (ServiceValidationError, HomeAssistantError, Exception) as err:  # pylint: disable=broad-except
            _LOGGER.warning("Auto-update failed for %s: %s", name, err)

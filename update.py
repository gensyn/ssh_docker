"""Platform for update integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    DOMAIN, CONF_SERVICE, CONF_DOCKER_COMMAND,
    DOCKER_CREATE_EXECUTABLE, DOCKER_CREATE_TIMEOUT,
    DEFAULT_DOCKER_COMMAND,
)
from .sensor import _ssh_run

_LOGGER = logging.getLogger(__name__)


def _short_id(image_id: str) -> str:
    """Return a short (12-char) Docker image ID, stripping the ``sha256:`` prefix."""
    hex_part = image_id.removeprefix("sha256:")
    return hex_part[:12] if len(hex_part) >= 12 else hex_part


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SSH Docker update platform from a config entry."""
    update_entity = DockerContainerUpdateEntity(entry, hass)
    hass.data.setdefault(DOMAIN, {})[f"{entry.entry_id}_update"] = update_entity
    async_add_entities([update_entity])


class DockerContainerUpdateEntity(UpdateEntity):
    """Update entity for a Docker container on a remote host."""

    _attr_has_entity_name = True
    _attr_translation_key = "update"
    _attr_should_poll = False
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    def __init__(self, entry: ConfigEntry, hass: HomeAssistant) -> None:
        """Initialize the update entity."""
        super().__init__()
        self.entry = entry
        self.hass = hass
        self._name = entry.data[CONF_NAME]
        self._service = entry.data.get(CONF_SERVICE, self._name)
        self._attr_unique_id = f"{entry.entry_id}_update"
        self.entity_id = generate_entity_id(
            "update.ssh_docker_{}", slugify(self._name), hass=hass
        )
        self._attr_title = self._name
        self._attr_installed_version: str | None = None
        self._attr_latest_version: str | None = None
        self._attr_in_progress: bool = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="SSH Docker",
            model="Docker Container",
            name=self._name,
        )

    def set_update_state(
            self,
            update_available: bool,
            installed_image_id: str | None,
            latest_image_id: str | None = None,
    ) -> None:
        """Update the entity state based on sensor data.

        Called by DockerContainerSensor after each successful poll.
        ``update_available=True`` sets latest_version to a value different from
        installed_version so HA reports the entity state as ON (update available).
        Both versions are shown as short (12-char) Docker image IDs.
        """
        if installed_image_id:
            installed_short = _short_id(installed_image_id)
            self._attr_installed_version = installed_short
            if update_available and latest_image_id:
                self._attr_latest_version = _short_id(latest_image_id)
            else:
                self._attr_latest_version = installed_short
        else:
            # Container unreachable — reset versions so state is unknown
            self._attr_installed_version = None
            self._attr_latest_version = None
        self.async_write_ha_state()

    async def async_install(
            self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install the update by recreating the container via docker_create."""
        options = dict(self.entry.options)
        name = self._service
        _LOGGER.debug("Update install requested for container %s", name)

        self._attr_in_progress = True
        self.async_write_ha_state()

        try:
            check_cmd = (
                f"command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1 && echo found"
                f" || (test -f /usr/bin/{DOCKER_CREATE_EXECUTABLE} && echo found || echo not_found)"
            )
            try:
                output, _ = await _ssh_run(self.hass, options, check_cmd)
                if output.strip() != "found":
                    _LOGGER.error(
                        "Update install for %s: %s not found on host",
                        name,
                        DOCKER_CREATE_EXECUTABLE,
                    )
                    raise ServiceValidationError(
                        f"{DOCKER_CREATE_EXECUTABLE} not found on host",
                        translation_domain=DOMAIN,
                        translation_key="docker_create_not_found",
                    )
            except (ServiceValidationError, HomeAssistantError):
                raise
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.error("Update install for %s: SSH error: %s", name, err)
                raise HomeAssistantError(
                    f"SSH error while checking for docker_create: {err}"
                ) from err

            create_cmd = (
                f"if command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1;"
                f" then {DOCKER_CREATE_EXECUTABLE} {name};"
                f" else /usr/bin/{DOCKER_CREATE_EXECUTABLE} {name}; fi"
            )
            _, exit_status = await _ssh_run(
                self.hass, options, create_cmd, timeout=DOCKER_CREATE_TIMEOUT
            )
            if exit_status != 0:
                _LOGGER.warning(
                    "Update install: %s exited with status %s for container %s; "
                    "the container may still have been recreated — check the sensor state",
                    DOCKER_CREATE_EXECUTABLE,
                    exit_status,
                    name,
                )
            else:
                _LOGGER.info("Update install: successfully recreated container %s", name)
        finally:
            self._attr_in_progress = False
            self.async_write_ha_state()
            # Trigger a sensor refresh so the new state is reflected quickly.
            sensor = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
            if sensor is not None:
                sensor.async_schedule_update_ha_state(force_refresh=True)

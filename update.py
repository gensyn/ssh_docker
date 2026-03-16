"""Platform for update integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DOMAIN, CONF_SERVICE
from .coordinator import SshDockerCoordinator

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
    coordinator: SshDockerCoordinator = hass.data.setdefault(DOMAIN, {}).setdefault(
        entry.entry_id, SshDockerCoordinator(hass, entry)
    )
    update_entity = DockerContainerUpdateEntity(coordinator, entry, hass)
    async_add_entities([update_entity])


class DockerContainerUpdateEntity(UpdateEntity):
    """Update entity for a Docker container on a remote host.

    Listens to coordinator data changes; delegates install to the coordinator.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "update"
    _attr_should_poll = False
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    def __init__(
        self,
        coordinator: SshDockerCoordinator,
        entry: ConfigEntry,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the update entity."""
        super().__init__()
        self.coordinator = coordinator
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

    async def async_added_to_hass(self) -> None:
        """Register coordinator listener so update state stays in sync."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """Propagate coordinator data changes to the update entity."""
        data = self.coordinator.data
        self.set_update_state(
            data.get("update_available", False),
            data.get("installed_image_id"),
            data.get("latest_image_id"),
        )

    def set_update_state(
            self,
            update_available: bool,
            installed_image_id: str | None,
            latest_image_id: str | None = None,
    ) -> None:
        """Update the entity state based on coordinator data.

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
        """Install the update by re-creating the container via the coordinator."""
        _LOGGER.debug("Update install requested for container %s", self._service)

        self._attr_in_progress = True
        self.async_write_ha_state()

        try:
            await self.coordinator.create()
        finally:
            self._attr_in_progress = False
            self.async_write_ha_state()
            # Refresh coordinator so the new container state is reflected quickly.
            await self.coordinator.async_request_refresh()

"""Platform for sensor integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_HOST, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, CoreState
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DOMAIN, CONF_SERVICE
from .coordinator import SshDockerCoordinator, STATE_UNKNOWN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=24)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SSH Docker sensor platform from a config entry."""
    coordinator: SshDockerCoordinator = hass.data[DOMAIN][entry.entry_id]
    sensor = DockerContainerSensor(coordinator, entry, hass)
    async_add_entities([sensor])


class DockerContainerSensor(SensorEntity):
    """Sensor representing a Docker container on a remote host.

    All I/O is delegated to the ``SshDockerCoordinator``; this class only
    reflects the coordinator's state in the HA entity model.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "state"
    _attr_should_poll = True

    def __init__(
        self,
        coordinator: SshDockerCoordinator,
        entry: ConfigEntry,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.coordinator = coordinator
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="SSH Docker",
            model="Docker Container",
            name=self._name,
        )

    @property
    def native_value(self) -> str:
        """Return current state, preferring coordinator's pending state when set."""
        return self.coordinator.pending_state or self.coordinator.data.get(
            "state", STATE_UNKNOWN
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return state attributes sourced from the coordinator."""
        return self.coordinator.data.get("attributes", {})

    async def async_added_to_hass(self) -> None:
        """Register coordinator listener and schedule the first refresh."""
        await super().async_added_to_hass()

        # When coordinator data changes (including pending state transitions),
        # push the new state to HA immediately without waiting for the next poll.
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

        # Show a transitional state so the UI doesn't sit on "unknown" while
        # the first SSH fetch is queued/in-progress.
        self.coordinator.set_pending_state("initializing")

        _host = self.entry.options.get(CONF_HOST, "")

        # Stagger only applies during HA startup, to spread SSH load across all
        # entries on the same host.  When HA is already running (e.g. a new entry
        # was added at runtime), skip the stagger so the container initializes
        # immediately instead of waiting up to N-1 seconds.
        if self.hass.state == CoreState.running:
            stagger_secs = 0
        else:
            _same_host_count = sum(
                1 for e in self.hass.config_entries.async_entries(DOMAIN)
                if e.options.get(CONF_HOST, "") == _host
            )
            stagger_secs = abs(hash(self.entry.entry_id)) % max(_same_host_count, 1)

        async def _staggered_update(_event=None):
            if stagger_secs > 0:
                await asyncio.sleep(stagger_secs)
            await self.async_update_ha_state(force_refresh=True)

        if self.hass.state == CoreState.running:
            self.hass.async_create_task(_staggered_update())
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _staggered_update)

    async def async_update(self) -> None:
        """Delegate data fetching to the coordinator."""
        await self.coordinator.async_request_refresh()

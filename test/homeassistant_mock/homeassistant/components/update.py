"""Mock for homeassistant.components.update."""

from enum import IntFlag


class UpdateEntityFeature(IntFlag):
    """Supported features of the update entity."""

    INSTALL = 1
    BACKUP = 2
    RELEASE_NOTES = 4
    PROGRESS = 8
    SPECIFIC_VERSION = 16


class UpdateEntity:
    """Mock UpdateEntity base class."""

    _attr_has_entity_name = False
    _attr_translation_key = None
    _attr_should_poll = True
    _attr_title: str | None = None
    _attr_installed_version: str | None = None
    _attr_latest_version: str | None = None
    _attr_in_progress: bool = False
    _attr_unique_id = None
    _attr_device_info = None
    _attr_supported_features: UpdateEntityFeature = UpdateEntityFeature(0)

    def __init__(self):
        """Initialize the update entity."""
        self.hass = None
        self.entity_id = None

    def async_write_ha_state(self):
        """Mock write HA state - no-op in tests."""

    def async_schedule_update_ha_state(self, force_refresh: bool = False):
        """Mock schedule HA state update - no-op in tests."""

    async def async_update_ha_state(self, force_refresh: bool = False):
        """Mock async update HA state - no-op in tests."""

    async def async_added_to_hass(self):
        """Mock async_added_to_hass - no-op in tests."""

    async def async_install(self, version, backup, **kwargs):
        """Mock install - subclasses should override."""

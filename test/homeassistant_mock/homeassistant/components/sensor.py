class SensorEntity:
    """Mock SensorEntity base class."""

    _attr_has_entity_name = False
    _attr_translation_key = None
    _attr_should_poll = True
    _attr_native_value = None
    _attr_extra_state_attributes = {}
    _attr_unique_id = None
    _attr_device_info = None

    def __init__(self):
        """Initialize the sensor entity."""
        self.hass = None
        self.entity_id = None

    def async_write_ha_state(self):
        """Mock write HA state - no-op in tests."""

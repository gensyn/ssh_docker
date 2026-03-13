class _RegistryEntry:
    """Mock entity registry entry."""

    def __init__(self, config_entry_id=None):
        """Initialize the entry."""
        self.config_entry_id = config_entry_id


class _Registry:
    """Mock entity registry."""

    def async_get(self, entity_id):
        """Return None by default - no entities registered in mock."""
        return None


def async_get(hass):
    """Return a mock entity registry."""
    return _Registry()

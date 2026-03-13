class DeviceInfo:
    """Mock DeviceInfo class."""

    def __init__(self, identifiers=None, manufacturer=None, model=None, name=None):
        """Initialize device info."""
        self.identifiers = identifiers
        self.manufacturer = manufacturer
        self.model = model
        self.name = name

class HomeAssistant:
    """Mock HomeAssistant class."""

    def __init__(self):
        """Initialize Home Assistant."""
        self.services = None
        self.data = {}
        self.config_entries = None


class ServiceCall:
    """Mock ServiceCall class."""

    def __init__(self, data=None):
        """Initialize the service call."""
        self.data = data or {}


class SupportsResponse:
    """Mock SupportsResponse enum."""

    ONLY = "only"
    OPTIONAL = "optional"
    NONE = "none"


ServiceResponse = dict


def callback(func):
    """Mock callback decorator - returns the function unchanged."""
    return func

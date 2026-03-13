"""Mock for homeassistant.components.http."""


class StaticPathConfig:
    """Mock StaticPathConfig."""

    def __init__(self, url, path, cache_headers=True):
        """Initialize."""
        self.url = url
        self.path = path
        self.cache_headers = cache_headers

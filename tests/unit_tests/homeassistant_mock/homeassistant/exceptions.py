class HomeAssistantError(Exception):
    """Mock HomeAssistantError base class."""


class ServiceValidationError(HomeAssistantError):
    """Mock ServiceValidationError."""

    def __init__(self, message="", translation_domain="", translation_key=""):
        """Initialize the error."""
        super().__init__(message)
        self.translation_domain = translation_domain
        self.translation_key = translation_key

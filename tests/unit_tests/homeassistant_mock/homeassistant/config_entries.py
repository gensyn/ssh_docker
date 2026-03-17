class AbortFlowException(Exception):
    """Raised when a config flow should be aborted."""

    def __init__(self, reason):
        """Initialize the exception."""
        super().__init__(reason)
        self.reason = reason


SOURCE_DISCOVERY = "discovery"

ConfigFlowResult = dict


class ConfigEntry:
    """Mock ConfigEntry."""

    def __init__(self, entry_id="test_entry_id", data=None, options=None):
        """Initialize the config entry."""
        self.entry_id = entry_id
        self.data = data or {}
        self.options = options or {}


class OptionsFlow:
    """Mock OptionsFlow base class."""

    def __init__(self):
        """Initialize the options flow."""
        self.config_entry = None
        self.hass = None

    def async_create_entry(self, data):
        """Create a config entry."""
        return {"type": "create_entry", "data": data}

    def async_show_form(self, step_id, data_schema=None, errors=None):
        """Show a form."""
        return {"type": "form", "step_id": step_id, "errors": errors or {}}


class ConfigFlow:
    """Mock ConfigFlow base class."""

    def __init_subclass__(cls, domain=None, **kwargs):
        """Register the domain."""
        super().__init_subclass__(**kwargs)
        if domain is not None:
            cls.DOMAIN = domain

    def __init__(self):
        """Initialize the config flow."""
        self.hass = None
        self.context = {}
        self._unique_id = None

    def async_abort(self, reason):
        """Return an abort result."""
        return {"type": "abort", "reason": reason}

    def async_create_entry(self, title, data, options=None):
        """Return a create entry result."""
        result = {"type": "create_entry", "title": title, "data": data}
        if options is not None:
            result["options"] = options
        return result

    def async_show_form(self, step_id, data_schema=None, errors=None):
        """Return a show form result."""
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def _async_current_entries(self):
        """Return current entries."""
        return []

    async def async_set_unique_id(self, unique_id, *, raise_on_progress=True):
        """Set the unique ID for this flow."""
        if raise_on_progress and getattr(self, "_force_abort_already_in_progress", False):
            raise AbortFlowException("already_in_progress")
        self._unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        """Abort if the unique ID is already configured."""
        if getattr(self, "_force_abort_unique_id", False):
            raise AbortFlowException("already_configured")

"""Helpers for reading and repairing config-entry data."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME

from .const import CONF_SERVICE


def get_entry_name(entry: ConfigEntry) -> str:
    """Return the best available friendly name for a config entry."""
    return (
        entry.data.get(CONF_NAME)
        or getattr(entry, "title", "")
        or entry.data.get(CONF_SERVICE, "")
        or entry.entry_id
    )


def get_entry_service(entry: ConfigEntry) -> str:
    """Return the Docker service name for a config entry."""
    return entry.data.get(CONF_SERVICE) or get_entry_name(entry)

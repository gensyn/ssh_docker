"""Mock for homeassistant.components.panel_custom."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def async_register_panel(
    hass: "HomeAssistant",
    *,
    webcomponent_name: str | None = None,
    component_name: str | None = None,
    sidebar_title: str | None = None,
    sidebar_icon: str | None = None,
    frontend_url_path: str | None = None,
    config: dict[str, Any] | None = None,
    require_admin: bool = False,
    module_url: str | None = None,
    embed_iframe: bool = False,
    trust_external_script: bool = False,
    html_url: str | None = None,
) -> None:
    """Register a custom panel (mock)."""

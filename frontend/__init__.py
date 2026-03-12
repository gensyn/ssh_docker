"""SSH Docker JavaScript module registration."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from ..const import URL_BASE, SSH_DOCKER_CARDS  # noqa: TID252

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "ssh_docker"
PANEL_ELEMENT_NAME = "ssh-docker-panel"
PANEL_SIDEBAR_TITLE = "SSH Docker"
PANEL_SIDEBAR_ICON = "mdi:docker"


class SshDockerPanelRegistration:
    """Register the SSH Docker Lovelace panel resource and sidebar panel."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise."""
        self.hass = hass
        self.lovelace = self.hass.data.get("lovelace")
        if self.lovelace and hasattr(self.lovelace, "resource_mode"):
            self.resource_mode = self.lovelace.resource_mode
        elif self.lovelace:
            # Backwards compatibility before 2026.2
            self.resource_mode = self.lovelace.mode
        else:
            self.resource_mode = None

    async def async_register(self) -> None:
        """Register the SSH Docker panel resource and sidebar panel."""
        from homeassistant.components.lovelace import MODE_STORAGE  # noqa: PLC0415
        await self._async_register_path()
        if self.resource_mode == MODE_STORAGE and self.lovelace:
            await self._async_register_modules()
        await self._async_register_panel()

    async def _async_register_panel(self) -> None:
        """Register the SSH Docker panel in the Home Assistant sidebar."""
        from homeassistant.components.panel_custom import async_register_panel  # noqa: PLC0415
        module_url = f"{URL_BASE}/{SSH_DOCKER_CARDS[0]['filename']}"
        try:
            await async_register_panel(
                self.hass,
                component_name=PANEL_ELEMENT_NAME,
                sidebar_title=PANEL_SIDEBAR_TITLE,
                sidebar_icon=PANEL_SIDEBAR_ICON,
                frontend_url_path=PANEL_URL_PATH,
                config={},
                require_admin=False,
                module_url=module_url,
            )
            _LOGGER.debug("Registered SSH Docker sidebar panel at /%s", PANEL_URL_PATH)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug("Failed to register SSH Docker sidebar panel: %s", exc)

    async def _async_register_path(self) -> None:
        """Register resource path if not already registered."""
        from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, str(Path(__file__).parent), False)]
            )
            _LOGGER.debug("Registered resource path from %s", Path(__file__).parent)
        except RuntimeError:
            _LOGGER.debug("Resource path already registered")

    async def _async_register_modules(self) -> None:
        """Register Lovelace modules if not already registered."""
        _LOGGER.debug("Installing SSH Docker javascript modules")

        resources = [
            resource
            for resource in self.lovelace.resources.async_items()
            if resource["url"].startswith(URL_BASE)
        ]

        for module in SSH_DOCKER_CARDS:
            url = f"{URL_BASE}/{module.get('filename')}"
            card_registered = False

            for resource in resources:
                if self._get_resource_path(resource["url"]) == url:
                    card_registered = True
                    if self._get_resource_version(resource["url"]) != module.get("version"):
                        _LOGGER.debug(
                            "Updating %s to version %s",
                            module.get("name"),
                            module.get("version"),
                        )
                        await self.lovelace.resources.async_update_item(
                            resource.get("id"),
                            {"res_type": "module", "url": url + "?v=" + module.get("version")},
                        )
                        await self.async_remove_gzip_files()
                    else:
                        _LOGGER.debug(
                            "%s already registered as version %s",
                            module.get("name"),
                            module.get("version"),
                        )

            if not card_registered:
                _LOGGER.debug(
                    "Registering %s as version %s",
                    module.get("name"),
                    module.get("version"),
                )
                await self.lovelace.resources.async_create_item(
                    {"res_type": "module", "url": url + "?v=" + module.get("version")}
                )

    def _get_resource_path(self, url: str) -> str:
        """Extract the path from a resource URL."""
        return url.split("?")[0]

    def _get_resource_version(self, url: str) -> str:
        """Extract the version from a resource URL."""
        parts = url.split("?")
        if len(parts) > 1:
            return parts[1].replace("v=", "")
        return "0"

    async def async_unregister(self) -> None:
        """Unload lovelace module resource."""
        from homeassistant.components.lovelace import MODE_STORAGE  # noqa: PLC0415
        if self.resource_mode == MODE_STORAGE and self.lovelace:
            for module in SSH_DOCKER_CARDS:
                url = f"{URL_BASE}/{module.get('filename')}"
                ssh_docker_resources = [
                    resource
                    for resource in self.lovelace.resources.async_items()
                    if str(resource["url"]).startswith(url)
                ]
                for resource in ssh_docker_resources:
                    await self.lovelace.resources.async_delete_item(resource.get("id"))

    async def async_remove_gzip_files(self) -> None:
        """Remove cached gzip files."""
        await self.hass.async_add_executor_job(self.remove_gzip_files)

    def remove_gzip_files(self) -> None:
        """Remove cached gzip files."""
        path = self.hass.config.path("custom_components/ssh_docker/frontend")
        try:
            gzip_files = [f for f in os.listdir(path) if f.endswith(".gz")]
            for file in gzip_files:
                try:
                    if (
                        Path.stat(Path(f"{path}/{file}")).st_mtime
                        < Path.stat(Path(f"{path}/{file.replace('.gz', '')}")).st_mtime
                    ):
                        _LOGGER.debug("Removing older gzip file - %s", file)
                        Path.unlink(Path(f"{path}/{file}"))
                except OSError:
                    pass
        except OSError:
            pass

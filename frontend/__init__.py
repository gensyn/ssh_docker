"""SSH Docker JavaScript module registration."""

import logging
import os
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import MODE_STORAGE
from homeassistant.components.panel_custom import async_register_panel
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..const import URL_BASE, SSH_DOCKER_CARDS, SSH_DOCKER_PANEL  # noqa: TID252

_LOGGER = logging.getLogger(__name__)


class SshDockerPanelRegistration:
    """Register SSH Docker JavaScript modules and sidebar panel."""

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
        """Register resource path, Lovelace modules, and sidebar panel."""
        await self._async_register_path()
        if self.resource_mode == MODE_STORAGE and self.lovelace:
            await self._async_register_modules()
        await self._async_register_panel()

    async def _async_register_path(self) -> None:
        """Register resource path if not already registered."""
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

    async def _async_register_panel(self) -> None:
        """Register the SSH Docker panel in the Home Assistant sidebar."""
        try:
            await async_register_panel(
                self.hass,
                webcomponent_name=SSH_DOCKER_PANEL["webcomponent_name"],
                frontend_url_path=SSH_DOCKER_PANEL["frontend_url_path"],
                module_url=f"{URL_BASE}/{SSH_DOCKER_PANEL['filename']}",
                sidebar_title=SSH_DOCKER_PANEL["sidebar_title"],
                sidebar_icon=SSH_DOCKER_PANEL["sidebar_icon"],
                require_admin=False,
            )
            _LOGGER.debug("Registered SSH Docker sidebar panel")
        except HomeAssistantError:
            _LOGGER.debug("SSH Docker panel already registered")

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

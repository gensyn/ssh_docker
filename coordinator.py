"""Coordinator for the SSH Docker integration.

The SshDockerCoordinator is the single owner of all I/O for one container
entry.  It exposes:

* ``data``            – latest fetched state / attributes dict
* ``set_pending_state`` – immediately show a transitional state in the UI
* ``async_request_refresh`` – fetch fresh state, clear pending, notify
* action coroutines  – ``restart``, ``stop``, ``remove``, ``create``
* listener management – ``async_add_listener`` / ``_async_notify_listeners``

Entities read from ``coordinator.data`` and register listeners so they are
notified whenever state changes.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import (
    DOMAIN, CONF_SERVICE, CONF_KEY_FILE, CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS,
    CONF_DOCKER_COMMAND, CONF_AUTO_UPDATE, CONF_CHECK_FOR_UPDATES, CONF_UPDATE_AVAILABLE,
    CONF_CREATED, CONF_IMAGE,
    SSH_COMMAND_DOMAIN, SSH_COMMAND_SERVICE_EXECUTE,
    SSH_CONF_OUTPUT, SSH_CONF_EXIT_STATUS,
    DEFAULT_DOCKER_COMMAND, DEFAULT_CHECK_KNOWN_HOSTS, DEFAULT_TIMEOUT,
    DOCKER_CREATE_EXECUTABLE, DOCKER_CREATE_TIMEOUT, DOCKER_PULL_TIMEOUT,
    get_ssh_semaphore,
)

_LOGGER = logging.getLogger(__name__)

_SCAN_INTERVAL = timedelta(hours=24)

STATE_UNAVAILABLE = "unavailable"
STATE_UNKNOWN = "unknown"

# Cache docker_create availability per host to avoid redundant SSH calls when
# many coordinators share the same remote host.  TTL matches the scan interval.
_DOCKER_CREATE_CACHE: dict[str, tuple[bool, float]] = {}
_DOCKER_CREATE_CACHE_TTL = _SCAN_INTERVAL.total_seconds()


async def _ssh_run(
    hass: HomeAssistant,
    options: dict[str, Any],
    command: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[str, int]:
    """Execute a command via ssh_command service.  Returns (stdout, exit_status).

    Concurrent executions to the same remote host are limited by a per-host
    semaphore (see get_ssh_semaphore in const.py).
    """
    _LOGGER.debug(
        "Running SSH command on %s: %s", options.get(CONF_HOST, "<unknown>"), command
    )
    service_data: dict[str, Any] = {
        CONF_HOST: options[CONF_HOST],
        CONF_USERNAME: options[CONF_USERNAME],
        "check_known_hosts": options.get(CONF_CHECK_KNOWN_HOSTS, DEFAULT_CHECK_KNOWN_HOSTS),
        "command": command,
        "timeout": timeout,
    }
    if options.get(CONF_PASSWORD):
        service_data[CONF_PASSWORD] = options[CONF_PASSWORD]
    if options.get(CONF_KEY_FILE):
        service_data["key_file"] = options[CONF_KEY_FILE]
    if options.get(CONF_KNOWN_HOSTS):
        service_data["known_hosts"] = options[CONF_KNOWN_HOSTS]

    async with get_ssh_semaphore(options[CONF_HOST]):
        response = await hass.services.async_call(
            SSH_COMMAND_DOMAIN,
            SSH_COMMAND_SERVICE_EXECUTE,
            service_data,
            blocking=True,
            return_response=True,
        )
    output = (response or {}).get(SSH_CONF_OUTPUT, "").strip()
    exit_status = (response or {}).get(SSH_CONF_EXIT_STATUS, 1)
    # asyncssh returns None for signal-based terminations; normalize to -1
    if exit_status is None:
        exit_status = -1
    _LOGGER.debug(
        "SSH command on %s exited with status %s",
        options.get(CONF_HOST, "<unknown>"),
        exit_status,
    )
    return output, exit_status


class SshDockerCoordinator:
    """Per-entry coordinator that owns all I/O for one Docker container.

    Preferred HA pattern: coordinator (or "client") owns I/O, entities
    reflect state.  Services interact with the coordinator; entities read
    from ``coordinator.data``.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self._name: str = entry.data[CONF_NAME]
        self._service: str = entry.data.get(CONF_SERVICE, self._name)
        self._pending_state: str | None = None
        self._in_auto_update: bool = False
        _host = entry.options.get(CONF_HOST, "")
        self.data: dict[str, Any] = {
            "state": STATE_UNKNOWN,
            "attributes": {"name": self._name, "host": _host},
            "update_available": False,
            "installed_image_id": None,
            "latest_image_id": None,
        }
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Listener management
    # ------------------------------------------------------------------

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register *listener*; returns an unsubscribe callable."""
        self._listeners.append(listener)

        def _remove() -> None:
            self._listeners.remove(listener)

        return _remove

    def _async_notify_listeners(self) -> None:
        """Call every registered listener."""
        for listener in self._listeners:
            listener()

    # ------------------------------------------------------------------
    # Transitional / pending state
    # ------------------------------------------------------------------

    def set_pending_state(self, state: str) -> None:
        """Set a transitional state and immediately notify all listeners.

        Entities return ``_pending_state`` from ``native_value`` (when set)
        so the UI reflects the transition before the next real fetch.
        """
        _LOGGER.debug(
            "Container %s entering transitional state: %s", self._name, state
        )
        self._pending_state = state
        self._async_notify_listeners()

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    async def async_request_refresh(self) -> None:
        """Fetch fresh state from the remote host, clear pending state, notify."""
        await self._async_fetch_data()
        self._pending_state = None
        self._async_notify_listeners()

    async def _async_fetch_data(self) -> None:
        """Fetch the container state from the remote host via SSH."""
        options = dict(self.entry.options)
        docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
        service = self._service
        host = options.get(CONF_HOST, "")
        _LOGGER.debug("Fetching data for container %s", service)

        info_cmd = (
            f"{docker_cmd} inspect {service}"
            f" --format '{{{{.State.Status}}}};{{{{.Created}}}};{{{{.Config.Image}}}};{{{{.Image}}}}'"
        )
        try:
            output, exit_status = await _ssh_run(self.hass, options, info_cmd)
        except (ServiceValidationError, HomeAssistantError, Exception) as err:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to inspect container %s: %s", service, err)
            self.data = {
                "state": STATE_UNAVAILABLE,
                "attributes": {
                    "name": self._name,
                    "host": host,
                    "docker_create_available": False,
                },
                "update_available": False,
                "installed_image_id": None,
                "latest_image_id": None,
            }
            return

        if exit_status != 0 or not output:
            _LOGGER.debug(
                "Container %s not found or docker inspect returned no output (exit status %d)",
                service,
                exit_status,
            )
            docker_create_available = await self._check_docker_create_available(options)
            self.data = {
                "state": STATE_UNAVAILABLE,
                "attributes": {
                    "name": self._name,
                    "host": host,
                    "docker_create_available": docker_create_available,
                },
                "update_available": False,
                "installed_image_id": None,
                "latest_image_id": None,
            }
            return

        parts = output.split(";", 3)
        if len(parts) < 4:
            _LOGGER.warning(
                "Unexpected docker inspect output format for container %s: %r",
                service,
                output,
            )
            docker_create_available = await self._check_docker_create_available(options)
            self.data = {
                "state": STATE_UNAVAILABLE,
                "attributes": {
                    "name": self._name,
                    "host": host,
                    "docker_create_available": docker_create_available,
                },
                "update_available": False,
                "installed_image_id": None,
                "latest_image_id": None,
            }
            return

        container_state, created, image_name, old_image_id = parts

        update_available = False
        new_image_id: str | None = None
        if options.get(CONF_CHECK_FOR_UPDATES, False):
            pull_cmd = (
                f"{docker_cmd} pull {image_name} > /dev/null 2>&1;"
                f" {docker_cmd} image inspect {image_name} --format '{{{{.Id}}}}'"
            )
            try:
                new_image_id, _ = await _ssh_run(
                    self.hass, options, pull_cmd, timeout=DOCKER_PULL_TIMEOUT
                )
                update_available = bool(new_image_id) and new_image_id != old_image_id.strip()
                if update_available:
                    _LOGGER.info(
                        "Update available for container %s: image %s has a newer version",
                        service,
                        image_name,
                    )
            except (ServiceValidationError, HomeAssistantError, Exception) as err:  # pylint: disable=broad-except
                _LOGGER.debug(
                    "Could not check for image updates for %s: %s", service, err
                )

        docker_create_available = await self._check_docker_create_available(options)

        _LOGGER.debug(
            "Container %s state: %s, update_available: %s",
            service,
            container_state,
            update_available,
        )
        self.data = {
            "state": container_state,
            "attributes": {
                "name": self._name,
                CONF_CREATED: created,
                CONF_IMAGE: image_name,
                CONF_UPDATE_AVAILABLE: update_available,
                "host": host,
                "docker_create_available": docker_create_available,
            },
            "update_available": update_available,
            "installed_image_id": old_image_id.strip(),
            "latest_image_id": new_image_id,
        }

        if update_available and options.get(CONF_AUTO_UPDATE, False) and not self._in_auto_update:
            self._in_auto_update = True
            try:
                await self._auto_recreate(options, service, docker_create_available)
                await self.async_request_refresh()
            finally:
                self._in_auto_update = False

    # ------------------------------------------------------------------
    # Action methods (called by services and update entity install)
    # ------------------------------------------------------------------

    async def restart(self) -> None:
        """Restart the container."""
        options = dict(self.entry.options)
        docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
        name = self._service
        _, exit_status = await _ssh_run(
            self.hass, options, f"{docker_cmd} restart {name}"
        )
        if exit_status != 0:
            _LOGGER.error(
                "Coordinator restart failed for container %s (exit status %d)",
                name,
                exit_status,
            )
            raise ServiceValidationError(
                f"Failed to restart container {name}",
                translation_domain=DOMAIN,
                translation_key="docker_command_failed",
            )
        _LOGGER.info("Coordinator: successfully restarted container %s", name)

    async def stop(self) -> None:
        """Stop the container."""
        options = dict(self.entry.options)
        docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
        name = self._service
        _, exit_status = await _ssh_run(
            self.hass, options, f"{docker_cmd} stop {name}"
        )
        if exit_status != 0:
            _LOGGER.error(
                "Coordinator stop failed for container %s (exit status %d)",
                name,
                exit_status,
            )
            raise ServiceValidationError(
                f"Failed to stop container {name}",
                translation_domain=DOMAIN,
                translation_key="docker_command_failed",
            )
        _LOGGER.info("Coordinator: successfully stopped container %s", name)

    async def remove(self) -> None:
        """Stop and remove the container."""
        options = dict(self.entry.options)
        docker_cmd = options.get(CONF_DOCKER_COMMAND, DEFAULT_DOCKER_COMMAND)
        name = self._service
        _, exit_status = await _ssh_run(
            self.hass,
            options,
            f"{docker_cmd} stop {name}; {docker_cmd} rm {name}",
        )
        if exit_status != 0:
            _LOGGER.error(
                "Coordinator remove failed for container %s (exit status %d)",
                name,
                exit_status,
            )
            raise ServiceValidationError(
                f"Failed to remove container {name}",
                translation_domain=DOMAIN,
                translation_key="docker_command_failed",
            )
        _LOGGER.info("Coordinator: successfully removed container %s", name)

    async def create(self) -> None:
        """Create (or re-create) the container using the docker_create executable."""
        options = dict(self.entry.options)
        name = self._service

        check_cmd = (
            f"command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1 && echo found"
            f" || (test -f /usr/bin/{DOCKER_CREATE_EXECUTABLE} && echo found || echo not_found)"
        )
        output, _ = await _ssh_run(self.hass, options, check_cmd)
        if output.strip() != "found":
            _LOGGER.error(
                "Coordinator create for container %s: %s not found on host",
                name,
                DOCKER_CREATE_EXECUTABLE,
            )
            raise ServiceValidationError(
                f"{DOCKER_CREATE_EXECUTABLE} not found on host",
                translation_domain=DOMAIN,
                translation_key="docker_create_not_found",
            )

        # Use if/then/else to run docker_create exactly once and preserve its exit code.
        create_cmd = (
            f"if command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1;"
            f" then {DOCKER_CREATE_EXECUTABLE} {name};"
            f" else /usr/bin/{DOCKER_CREATE_EXECUTABLE} {name}; fi"
        )
        _, exit_status = await _ssh_run(
            self.hass, options, create_cmd, timeout=DOCKER_CREATE_TIMEOUT
        )
        if exit_status != 0:
            # The docker_create script may exit non-zero for recoverable reasons
            # (e.g. cleanup commands that fail when the container does not yet exist)
            # while still successfully creating the container.  Log a warning and let
            # the follow-up refresh reveal the real container state.
            _LOGGER.warning(
                "Coordinator create: %s exited with status %s for container %s; "
                "the container may still have been created — check the sensor state",
                DOCKER_CREATE_EXECUTABLE,
                exit_status,
                name,
            )
        else:
            _LOGGER.info("Coordinator: successfully created container %s", name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _check_docker_create_available(self, options: dict[str, Any]) -> bool:
        """Return True if docker_create is present on the remote host.

        Results are cached per host for the duration of the scan interval so that
        coordinators sharing a host only incur one SSH round-trip per poll cycle.
        """
        host = options.get(CONF_HOST, "")
        now = time.monotonic()
        cached = _DOCKER_CREATE_CACHE.get(host)
        if cached is not None:
            result, ts = cached
            if now - ts < _DOCKER_CREATE_CACHE_TTL:
                return result

        check_cmd = (
            f"command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1 && echo found"
            f" || (test -f /usr/bin/{DOCKER_CREATE_EXECUTABLE} && echo found || echo not_found)"
        )
        try:
            output, _ = await _ssh_run(self.hass, options, check_cmd)
            result = output.strip() == "found"
        except (ServiceValidationError, HomeAssistantError, Exception) as err:  # pylint: disable=broad-except
            _LOGGER.debug("Could not check for docker_create on host: %s", err)
            result = False

        _DOCKER_CREATE_CACHE[host] = (result, now)
        return result

    async def _auto_recreate(
        self,
        options: dict[str, Any],
        name: str,
        docker_create_available: bool = False,
    ) -> None:
        """Recreate the container using docker_create if available."""
        if not docker_create_available:
            _LOGGER.warning(
                "Auto-update: docker_create not found on host for container %s", name
            )
            return
        create_cmd = (
            f"command -v {DOCKER_CREATE_EXECUTABLE} >/dev/null 2>&1"
            f" && {DOCKER_CREATE_EXECUTABLE} {name}"
            f" || /usr/bin/{DOCKER_CREATE_EXECUTABLE} {name}"
        )
        try:
            _, exit_status = await _ssh_run(self.hass, options, create_cmd)
            if exit_status != 0:
                _LOGGER.warning("Auto-update: docker_create failed for %s", name)
                return
            _LOGGER.info("Auto-update: recreated container %s", name)
        except (ServiceValidationError, HomeAssistantError, Exception) as err:  # pylint: disable=broad-except
            _LOGGER.warning("Auto-update failed for %s: %s", name, err)

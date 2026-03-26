"""Constants for the SSH Docker integration."""

import asyncio

DOMAIN = "ssh_docker"


CONF_SERVICE = "service"
CONF_KEY_FILE = "key_file"
CONF_CHECK_KNOWN_HOSTS = "check_known_hosts"
CONF_KNOWN_HOSTS = "known_hosts"
CONF_DOCKER_COMMAND = "docker_command"
CONF_AUTO_UPDATE = "auto_update"
CONF_CHECK_FOR_UPDATES = "check_for_updates"

CONF_UPDATE_AVAILABLE = "update_available"
CONF_CONTAINER_STATE = "container_state"
CONF_CREATED = "created"
CONF_IMAGE = "image"

SSH_COMMAND_DOMAIN = "ssh_command"
SSH_COMMAND_SERVICE_EXECUTE = "execute"

SSH_CONF_OUTPUT = "output"
SSH_CONF_ERROR = "error"
SSH_CONF_EXIT_STATUS = "exit_status"

SERVICE_CREATE = "create"
SERVICE_RESTART = "restart"
SERVICE_STOP = "stop"
SERVICE_REMOVE = "remove"
SERVICE_REFRESH = "refresh"
SERVICE_GET_LOGS = "get_logs"

DEFAULT_DOCKER_COMMAND = "docker"
DEFAULT_CHECK_KNOWN_HOSTS = True
DEFAULT_AUTO_UPDATE = False
DEFAULT_CHECK_FOR_UPDATES = False
DEFAULT_TIMEOUT = 60
DOCKER_CREATE_TIMEOUT = 600  # 10 minutes – container creation can take a long time
DOCKER_PULL_TIMEOUT = 600  # 10 minutes – pulling a large image can take a long time

DOCKER_SERVICES_EXECUTABLE = "docker_services"
DOCKER_CREATE_EXECUTABLE = "docker_create"

# Per-host semaphores that limit concurrent SSH calls to the same remote host.
# Using a per-host limit (rather than a single global one) prevents a busy host
# from starving sensors on other hosts, and keeps the number of simultaneous
# connections to any single SSH server low enough to avoid hitting sshd's
# MaxStartups / MaxSessions limits (which typically default to 10).
#
# asyncio.Semaphore can safely be created at module level in Python 3.10+
# (no running event loop required); Home Assistant requires Python 3.12+.
SSH_MAX_CONNECTIONS_PER_HOST = 3
_SSH_HOST_SEMAPHORES: dict[str, asyncio.Semaphore] = {}


def get_ssh_semaphore(host: str) -> asyncio.Semaphore:
    """Return the per-host SSH semaphore, creating it on first use.

    Thread-safety note: asyncio runs on a single thread, so concurrent access
    to _SSH_HOST_SEMAPHORES is not possible without an explicit context switch
    (await).  The lazy creation below is therefore safe.
    """
    if host not in _SSH_HOST_SEMAPHORES:
        _SSH_HOST_SEMAPHORES[host] = asyncio.Semaphore(SSH_MAX_CONNECTIONS_PER_HOST)
    return _SSH_HOST_SEMAPHORES[host]



URL_BASE = "/ssh_docker"
SSH_DOCKER_CARDS = [
    {
        "name": "SSH Docker Card",
        "filename": "ssh-docker-card.js",
        "version": "1.0.0",
    }
]
SSH_DOCKER_PANEL = {
    "webcomponent_name": "ssh-docker-panel",
    "frontend_url_path": "ssh-docker",
    "filename": "ssh-docker-panel.js",
    "sidebar_title": "SSH Docker",
    "sidebar_icon": "mdi:docker",
}

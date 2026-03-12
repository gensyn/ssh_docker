"""Constants for the SSH Docker integration."""

import asyncio

DOMAIN = "ssh_docker"

CONF_SERVICE = "service"
CONF_KEY_FILE = "key_file"
CONF_CHECK_KNOWN_HOSTS = "check_known_hosts"
CONF_KNOWN_HOSTS = "known_hosts"
CONF_DOCKER_COMMAND = "docker_command"
CONF_AUTO_UPDATE = "auto_update"

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

DEFAULT_DOCKER_COMMAND = "docker"
DEFAULT_CHECK_KNOWN_HOSTS = True
DEFAULT_AUTO_UPDATE = False
DEFAULT_TIMEOUT = 60
DOCKER_CREATE_TIMEOUT = 600  # 10 minutes – container creation can take a long time

DOCKER_SERVICES_EXECUTABLE = "docker_services"
DOCKER_CREATE_EXECUTABLE = "docker_create"

# Shared semaphore that limits the total number of concurrent SSH calls across
# all sensors and service handlers.  This prevents overloading the ssh_command
# integration (and the remote host) when many containers are configured.
# asyncio.Semaphore can safely be created at module level in Python 3.10+
# (no running event loop required); Home Assistant requires Python 3.12+.
_SSH_SEMAPHORE = asyncio.Semaphore(10)

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

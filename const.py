"""Constants for the SSH Docker integration."""

DOMAIN = "ssh_docker"

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

DOCKER_SERVICES_EXECUTABLE = "docker_services"
DOCKER_CREATE_EXECUTABLE = "docker_create"

URL_BASE = "/ssh_docker"
SSH_DOCKER_CARDS = [
    {
        "name": "SSH Docker Panel",
        "filename": "ssh-docker-panel.js",
        "version": "1.1.0",
    }
]

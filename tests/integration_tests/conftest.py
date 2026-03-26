"""pytest-homeassistant-custom-component conftest for SSH Docker integration tests.

This file wires the component (which lives at the repo root, not inside a
conventional ``custom_components/`` sub-directory) into Home Assistant's custom
component loader, and provides shared fixtures used by all integration tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

# The repo root IS the component package (content_in_root: true).
REPO_ROOT = Path(__file__).parent.parent.parent  # …/ssh_docker/ssh_docker/

# Make the repo root importable so Python can see it as a top-level package.
_REPO_PARENT = str(REPO_ROOT.parent)
if _REPO_PARENT not in sys.path:
    sys.path.insert(0, _REPO_PARENT)

# ---------------------------------------------------------------------------
# custom_components symlink
# ---------------------------------------------------------------------------
# Home Assistant's component loader imports the ``custom_components`` package
# and iterates its subdirectories.  We create a symlink
#   <repo_root>/custom_components/ssh_docker -> <repo_root>
# so that HA can discover and load the component as ``custom_components.ssh_docker``.

_CUSTOM_COMPONENTS = REPO_ROOT / "custom_components"
_CUSTOM_COMPONENTS.mkdir(exist_ok=True)
(_CUSTOM_COMPONENTS / "__init__.py").touch()

_SYMLINK = _CUSTOM_COMPONENTS / "ssh_docker"
if not _SYMLINK.exists():
    _SYMLINK.symlink_to(REPO_ROOT)

# ---------------------------------------------------------------------------
# ssh_command stub
# ---------------------------------------------------------------------------
# ssh_docker's manifest.json declares ``ssh_command`` as a dependency.
# HA's loader will refuse to set up ssh_docker if ssh_command can't be found.
# We create a minimal stub so the dependency can be resolved.  The stub's
# ``async_setup`` is a no-op; all actual SSH calls are intercepted by the
# ``mock_ssh`` fixture before they reach any service-call code.

_SSH_COMMAND_PKG = _CUSTOM_COMPONENTS / "ssh_command"
if not _SSH_COMMAND_PKG.exists():
    _SSH_COMMAND_PKG.mkdir(parents=True, exist_ok=True)
    (_SSH_COMMAND_PKG / "__init__.py").write_text(
        'async def async_setup(hass, config): return True\n'
    )
    (_SSH_COMMAND_PKG / "manifest.json").write_text(
        '{"domain": "ssh_command", "name": "SSH Command stub",'
        ' "version": "0.0.0", "documentation": "", "codeowners": [],'
        ' "requirements": [], "dependencies": [], "iot_class": "local_push"}\n'
    )

# Make custom_components importable from within the repo root.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Default SSH run mock helper
# ---------------------------------------------------------------------------


async def _default_ssh_run(hass, options, command, timeout=60):
    """Return safe defaults for every SSH command the component might issue.

    * docker inspect   → container is running, image sha matches (no update)
    * docker pull / image inspect → same sha as running container
    * docker_create check / run   → available ("found")
    * docker_services             → absent (non-zero exit, empty output)
    * all other docker commands   → success (exit 0, empty stdout)
    """
    if "docker inspect" in command and "image inspect" not in command:
        return "running;2024-01-01T00:00:00Z;nginx:latest;sha256:abc123456789def0", 0
    if "image inspect" in command or "docker pull" in command:
        return "sha256:abc123456789def0", 0
    if "docker_create" in command:
        return "found", 0
    if "docker_services" in command:
        # docker_services availability check and service-discovery commands
        # → return non-zero so the component treats docker_services as absent
        return "", 1
    # All other docker commands (restart, stop, rm, etc.) succeed
    return "", 0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for every test in this package."""


@pytest.fixture(autouse=True)
def mock_frontend_setup():
    """Skip sidebar panel registration — irrelevant for integration tests.

    ``async_setup`` calls ``SshDockerPanelRegistration.async_register`` which
    interacts with the lovelace subsystem.  We patch it to a no-op so the
    integration tests can focus on the component's business logic.
    """
    with patch(
        "custom_components.ssh_docker.SshDockerPanelRegistration"
    ) as mock_cls:
        mock_cls.return_value.async_register = AsyncMock()
        yield


@pytest.fixture(autouse=True)
def mock_ssh_stagger():
    """Remove stagger sleep delays from the sensor's first-update path.

    ``DockerContainerSensor.async_added_to_hass`` uses ``asyncio.sleep`` to
    stagger concurrent SSH calls from entries sharing the same host.  We patch
    it to a no-op so every test's initial state is ready immediately after
    ``await hass.async_block_till_done()``.
    """
    with patch(
        "custom_components.ssh_docker.sensor.asyncio.sleep",
        new=AsyncMock(),
    ):
        yield


@pytest.fixture(autouse=True)
def clear_caches():
    """Reset module-level per-host SSH caches before each test.

    ``_DOCKER_CREATE_CACHE`` and ``_DOCKER_SERVICES_CACHE`` are module-level
    dicts that persist across tests within the same process.  Clearing them
    ensures each test starts with a clean slate.
    """
    import custom_components.ssh_docker.coordinator as _coord  # noqa: PLC0415

    _coord._DOCKER_CREATE_CACHE.clear()
    _coord._DOCKER_SERVICES_CACHE.clear()
    yield
    _coord._DOCKER_CREATE_CACHE.clear()
    _coord._DOCKER_SERVICES_CACHE.clear()


@pytest.fixture()
def mock_ssh():
    """Patch *both* ``_ssh_run`` references with the default safe mock.

    The function is imported into ``__init__.py`` for ``_discover_services``
    *and* called directly from ``coordinator.py``.  Both references must be
    patched so no real SSH connection is ever attempted.
    """
    with patch(
        "custom_components.ssh_docker.coordinator._ssh_run",
        side_effect=_default_ssh_run,
    ), patch(
        "custom_components.ssh_docker._ssh_run",
        side_effect=_default_ssh_run,
    ):
        yield

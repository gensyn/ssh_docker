"""Test package for ssh_docker. Adds the homeassistant mock to sys.path."""
import sys
from pathlib import Path

_mock_path = str(Path(__file__).parent / "homeassistant_mock")
if _mock_path not in sys.path:
    sys.path.insert(0, _mock_path)

_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
if _plugin_path not in sys.path:
    sys.path.insert(0, _plugin_path)

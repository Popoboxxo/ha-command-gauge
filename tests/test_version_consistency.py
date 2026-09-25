"""The User-Agent must not carry a hardcoded version.

The 0.1.1 release bumped manifest.json and pyproject.toml but left
`"User-Agent": "ha-command-gauge/0.1.0"` in the client headers. Nothing
failed, nothing warned - the API was simply told the wrong version, and the
existing test_metadata only cross-checked manifest against pyproject.

These tests pin the User-Agent to the manifest so the three can never drift
apart again.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "command_gauge"
MANIFEST = json.loads((COMPONENT / "manifest.json").read_text())
VERSION = MANIFEST["version"]


def test_integration_version_reads_the_manifest() -> None:
    """The module-level constant must equal the manifest version."""
    from custom_components.command_gauge.coordinator import INTEGRATION_VERSION

    assert INTEGRATION_VERSION == VERSION


def test_no_hardcoded_version_in_user_agent() -> None:
    """A literal version in the headers is the bug this test exists for.

    Matches only a real version string, not the {INTEGRATION_VERSION}
    interpolation.
    """
    source = (COMPONENT / "coordinator.py").read_text()
    literals = [m for m in re.findall(r'"ha-command-gauge/([^"{]*)"', source) if m.strip()]
    assert not literals, (
        f"hardcoded version(s) found in coordinator.py: {literals} - "
        f"use INTEGRATION_VERSION (currently {VERSION})"
    )


def test_user_agent_uses_the_integration_version() -> None:
    """The f-string must interpolate, not repeat the version literally."""
    source = (COMPONENT / "coordinator.py").read_text()
    assert '"User-Agent": f"ha-command-gauge/{INTEGRATION_VERSION}"' in source
    assert source.count("INTEGRATION_VERSION") >= 2


def test_all_three_version_sources_agree() -> None:
    """manifest, pyproject and the module constant must be identical."""
    from custom_components.command_gauge.coordinator import INTEGRATION_VERSION

    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert f'version = "{VERSION}"' in pyproject
    assert INTEGRATION_VERSION == VERSION


def test_manifest_and_project_version_are_consistent() -> None:
    """Kept as an explicit guard: this is what CI failed on."""
    project = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert f'version = "{MANIFEST["version"]}"' in project

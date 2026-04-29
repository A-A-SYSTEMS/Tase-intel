"""Fixtures for lint tests."""
from pathlib import Path

import pytest


@pytest.fixture()
def repo_root() -> Path:
    """Resolve the project root by walking up until pyproject.toml is found."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("Could not find repo root (no pyproject.toml)")

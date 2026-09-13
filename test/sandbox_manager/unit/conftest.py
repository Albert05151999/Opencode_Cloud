from pathlib import Path

import pytest

from sandbox_manager.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    value = Registry(tmp_path / "registry.db")
    value.initialize()
    return value

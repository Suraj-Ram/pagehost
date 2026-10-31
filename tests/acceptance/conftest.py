from pathlib import Path

import pytest

from acceptance.app_driver import AppDriver
from acceptance.runner import Driver


@pytest.fixture
def driver(tmp_path: Path) -> Driver:
    """One isolated pagehost. Every acceptance scenario uses this fixture."""
    return AppDriver(tmp_path)

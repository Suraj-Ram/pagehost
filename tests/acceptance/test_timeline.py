"""The timeline directive, judged by the page a reader receives."""

from pathlib import Path

import pytest

from acceptance.app_driver import open_app
from acceptance.cases import TIMELINE_OF_DATES_AND_TIMES
from acceptance.runner import run
from acceptance.semantic import assert_semantic


@pytest.mark.acceptance
def test_timeline_of_dates_and_times(tmp_path: Path):
    html = run(open_app(tmp_path), TIMELINE_OF_DATES_AND_TIMES.operations)
    assert_semantic(
        html,
        TIMELINE_OF_DATES_AND_TIMES.blocks,
        title=TIMELINE_OF_DATES_AND_TIMES.title,
    )

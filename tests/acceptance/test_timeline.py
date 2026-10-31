"""The timeline directive, judged by the page a reader receives."""

from pathlib import Path

import pytest

from acceptance.app_driver import open_app
from acceptance.cases import TIMELINE_OF_DATES_AND_TIMES, TIMELINE_WITHOUT_STATUSES
from acceptance.runner import run
from acceptance.semantic import assert_semantic

_TIMELINES = (TIMELINE_OF_DATES_AND_TIMES, TIMELINE_WITHOUT_STATUSES)


@pytest.mark.acceptance
@pytest.mark.parametrize("scenario", _TIMELINES, ids=lambda scenario: scenario.name)
def test_timeline_page(scenario, tmp_path: Path):
    html = run(open_app(tmp_path), scenario.operations)
    assert_semantic(html, scenario.blocks, title=scenario.title)

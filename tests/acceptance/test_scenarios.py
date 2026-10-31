"""Each scenario builds one page and compares it as a reader would."""

import pytest

from acceptance.cases import (
    SCENARIOS,
    TIMELINE_OF_DATES_AND_TIMES,
    TIMELINE_WITHOUT_STATUSES,
)
from acceptance.runner import Driver, run
from acceptance.semantic import assert_semantic

_PAGES = (*SCENARIOS, TIMELINE_OF_DATES_AND_TIMES, TIMELINE_WITHOUT_STATUSES)


@pytest.mark.acceptance
@pytest.mark.parametrize("scenario", _PAGES, ids=lambda scenario: scenario.name)
def test_page_matches_semantic_html(scenario, driver: Driver):
    html = run(driver, scenario.operations)
    assert_semantic(html, scenario.blocks, title=scenario.title)

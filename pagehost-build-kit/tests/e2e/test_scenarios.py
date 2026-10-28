"""One test per scenario file in scenarios/. Each is: a list of tool calls, and the page they
must have produced. Run `pytest tests/e2e -k append` to pick some.

Scenarios marked `status: planned` describe features that are specified but not built yet.
They are expected to fail (strictly), so the day one starts passing the suite tells you to
flip it to `ready`."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from e2e.harness import runner
from e2e.harness.scenario import load_all

HERE = Path(__file__).resolve().parent
SCENARIOS = load_all(HERE / "scenarios")


def _param(s):
    marks = [pytest.mark.xfail(strict=True, reason="planned: specified, not implemented yet")] \
        if s.status == "planned" else []
    return pytest.param(s, id=s.name, marks=marks)


@pytest.mark.parametrize("scenario", [_param(s) for s in SCENARIOS])
def test_scenario(scenario, endpoint):
    async def go():
        async with endpoint.connect() as session:
            await runner.run(scenario, session, endpoint.fetch)

    asyncio.run(go())


def test_scenario_names_are_unique_and_match_their_file_names():
    names = [s.name for s in SCENARIOS]
    assert len(names) == len(set(names))
    for s in SCENARIOS:
        assert s.path.stem.split("-", 1)[1] == s.name, f"{s.path.name}: name should be {s.path.stem.split('-', 1)[1]!r}"
        assert s.status in ("ready", "planned")


def test_scenarios_only_use_tools_the_system_publicly_offers(endpoint):
    async def go():
        async with endpoint.connect() as session:
            return await session.tool_names()

    offered = asyncio.run(go())
    used = {step["call"] for s in SCENARIOS for step in s.steps}
    assert used <= offered, f"unknown tools: {used - offered}"

"""The runner applies operations in order and returns whatever the driver rendered."""

import pytest

from acceptance.operations import Append, Publish
from acceptance.runner import run
from acceptance.semantic import assert_semantic


class ScriptedDriver:
    def __init__(self, fragment: str) -> None:
        self._fragment = fragment
        self.applied: list[object] = []

    def apply(self, operation: object) -> None:
        self.applied.append(operation)

    def fragment(self) -> str:
        return self._fragment


def test_run_applies_operations_in_order_and_returns_the_fragment():
    driver = ScriptedDriver("<h2>Welcome</h2><ul><li>Write things down</li></ul>")
    publish = Publish(title="Team handbook", content="## Welcome")
    append = Append(content="- Write things down", section="welcome")

    html = run(driver, [publish, append])

    assert driver.applied == [publish, append]
    assert_semantic(html, [
        {"h2": "Welcome"},
        {"ul": ["Write things down"]},
    ])


def test_run_rejects_an_empty_operation_list():
    with pytest.raises(ValueError, match="at least one operation"):
        run(ScriptedDriver(""), [])

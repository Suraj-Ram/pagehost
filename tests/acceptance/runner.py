"""Apply a scenario's operations and return the HTML the driver rendered."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from acceptance.operations import Operation


class Driver(Protocol):
    """The system under test, scoped to a single page for one scenario.

    `fragment` may be the `<main>` contents or a full document. Comparison
    reads `<main>` when it is present and ignores the shell around it.
    """

    def apply(self, operation: Operation) -> None:
        """Perform one operation against the page this driver owns."""

    def fragment(self) -> str:
        """Return the HTML currently served for that page."""


def run(driver: Driver, operations: Sequence[Operation]) -> str:
    if not operations:
        raise ValueError("a scenario needs at least one operation")
    for operation in operations:
        driver.apply(operation)
    return driver.fragment()

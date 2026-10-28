"""Scenario catalogue.

Add a page by appending a `Scenario`: the operations that build it, and the
blocks a reader should see. Match content, not markup. The stylesheet, classes,
wrappers, and the page shell are not part of `blocks`.
"""

from acceptance.operations import Publish, Scenario

_HANDBOOK = """\
## Welcome

Welcome to the **team handbook**. It covers *how we work*, with `code` and a [link](https://example.com/docs).

## Principles

- Write things down
- Default to open
- Ship small changes

## Steps

1. Clone the repo
2. Run the tests
3. Open a pull request
""".removesuffix("\n")

PUBLISH_A_PAGE = Scenario(
    name="publish-a-page",
    title="Team handbook",
    operations=(
        Publish(title="Team handbook", content=_HANDBOOK),
    ),
    blocks=(
        {"h2": "Welcome"},
        {
            "p": (
                "Welcome to the **team handbook**. It covers *how we work*, "
                "with `code` and a [link](https://example.com/docs)."
            ),
        },
        {"h2": "Principles"},
        {"ul": ["Write things down", "Default to open", "Ship small changes"]},
        {"h2": "Steps"},
        {"ol": ["Clone the repo", "Run the tests", "Open a pull request"]},
    ),
)

SCENARIOS = (PUBLISH_A_PAGE,)

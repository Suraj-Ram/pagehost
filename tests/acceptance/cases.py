"""Scenario catalogue.

Add a page by appending a `Scenario`: the operations that build it, and the
blocks a reader should see. Match content, not markup. The stylesheet, classes,
wrappers, and the page shell are not part of `blocks`.
"""

from acceptance.operations import (
    Append,
    DeleteSection,
    Publish,
    ReplaceSection,
    ReplaceText,
    Rollback,
    Scenario,
)

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

_RELEASE_V1 = """\
## v1.0

- First release
""".removesuffix("\n")

_RELEASE_V11 = """\
## v1.1

- Bug fixes
""".removesuffix("\n")

APPEND_TO_THE_END = Scenario(
    name="append-to-the-end-of-a-page",
    title="Release notes",
    operations=(
        Publish(title="Release notes", content=_RELEASE_V1),
        Append(content=_RELEASE_V11),
    ),
    blocks=(
        {"h2": "v1.0"},
        {"ul": ["First release"]},
        {"h2": "v1.1"},
        {"ul": ["Bug fixes"]},
    ),
)

_PLAN = """\
## Plan

- Ship the beta

## Risks

- Vendor delay

### Mitigation

Use two vendors.

## Notes

Last updated by the team.
""".removesuffix("\n")

DELETE_A_SECTION = Scenario(
    name="delete-a-section",
    title="Project plan",
    operations=(
        Publish(title="Project plan", content=_PLAN),
        DeleteSection(section="risks"),
        DeleteSection(section="notes"),
    ),
    blocks=(
        {"h2": "Plan"},
        {"ul": ["Ship the beta"]},
    ),
)

_FENCE = "```"
_TOUR = f"""\
## Tour

> Measure twice, cut once.

| Region | Signups |
|---|---|
| North | 120 |
| South | 85 |

~~old~~ new text

{_FENCE}python
print("hello")
{_FENCE}

:::callout Heads up
Back up before migrating.
:::

:::details More info
Hidden **detail** text.
:::
""".removesuffix("\n")

MARKDOWN_FEATURE_TOUR = Scenario(
    name="markdown-feature-tour",
    title="Feature tour",
    operations=(Publish(title="Feature tour", content=_TOUR),),
    blocks=(
        {"h2": "Tour"},
        {"blockquote": "Measure twice, cut once."},
        {
            "table": {
                "head": ["Region", "Signups"],
                "rows": [["North", "120"], ["South", "85"]],
            },
        },
        {"p": "~~old~~ new text"},
        {"pre": 'print("hello")'},
        {
            "callout": {
                "kind": "note",
                "title": "Heads up",
                "text": "Back up before migrating.",
            },
        },
        {"details": {"summary": "More info", "text": "Hidden **detail** text."}},
    ),
)

_PLAN_WITH_NOTES = """\
## Plan

- Ship the beta

## Risks

- Vendor delay

## Notes

Last updated by the team.
""".removesuffix("\n")

_BUDGET = """\
## Budget

Funding is approved.
""".removesuffix("\n")

APPEND_INSIDE_A_SECTION = Scenario(
    name="append-inside-a-section-and-add-a-sibling",
    title="Project plan",
    operations=(
        Publish(title="Project plan", content=_PLAN_WITH_NOTES),
        Append(content="Pilot starts in March.", section="plan"),
        Append(content=_BUDGET, section="plan"),
    ),
    blocks=(
        {"h2": "Plan"},
        {"ul": ["Ship the beta"]},
        {"p": "Pilot starts in March."},
        {"h2": "Budget"},
        {"p": "Funding is approved."},
        {"h2": "Risks"},
        {"ul": ["Vendor delay"]},
        {"h2": "Notes"},
        {"p": "Last updated by the team."},
    ),
)

_RISKS_REPLACEMENT = """\
## Risks

None identified.
""".removesuffix("\n")

REPLACE_A_SECTION = Scenario(
    name="replace-a-section-including-its-subsections",
    title="Project plan",
    operations=(
        Publish(title="Project plan", content=_PLAN),
        ReplaceSection(section="risks", content=_RISKS_REPLACEMENT),
    ),
    blocks=(
        {"h2": "Plan"},
        {"ul": ["Ship the beta"]},
        {"h2": "Risks"},
        {"p": "None identified."},
        {"h2": "Notes"},
        {"p": "Last updated by the team."},
    ),
)

_NOTES_PAGE = """\
## Plan

Old plan.

## Notes

Keep me.
""".removesuffix("\n")

REPLACEMENT_WITHOUT_A_HEADING = Scenario(
    name="a-replacement-without-a-heading-is-flagged",
    title="Notes page",
    operations=(
        Publish(title="Notes page", content=_NOTES_PAGE),
        ReplaceSection(section="plan", content="New plan text, no heading."),
    ),
    blocks=(
        {"p": "New plan text, no heading."},
        {"h2": "Notes"},
        {"p": "Keep me."},
    ),
)

_OPTIONS = """\
## Option

Choose A.

## Option

Choose B.
""".removesuffix("\n")

DUPLICATE_HEADINGS = Scenario(
    name="duplicate-headings-get-numbered-section-ids",
    title="Options",
    operations=(
        Publish(title="Options", content=_OPTIONS),
        ReplaceText(old="Choose B.", new="Choose C.", section="option-2"),
    ),
    blocks=(
        {"h2": "Option"},
        {"p": "Choose A."},
        {"h2": "Option"},
        {"p": "Choose C."},
    ),
)

_BETA = """\
## Plan

- Ship the beta
""".removesuffix("\n")

_RISKS = """\
## Risks

- Vendor delay
""".removesuffix("\n")

ROLLBACK_RESTORES_AN_EARLIER_VERSION = Scenario(
    name="rollback-restores-an-earlier-version",
    title="Project plan",
    operations=(
        Publish(title="Project plan", content=_BETA),
        Append(content=_RISKS),
        ReplaceText(old="Ship the beta", new="Ship GA"),
        Rollback(to_version=1),
    ),
    blocks=(
        {"h2": "Plan"},
        {"ul": ["Ship the beta"]},
    ),
)

SCENARIOS = (
    PUBLISH_A_PAGE,
    APPEND_TO_THE_END,
    APPEND_INSIDE_A_SECTION,
    REPLACE_A_SECTION,
    REPLACEMENT_WITHOUT_A_HEADING,
    DELETE_A_SECTION,
    DUPLICATE_HEADINGS,
    ROLLBACK_RESTORES_AN_EARLIER_VERSION,
    MARKDOWN_FEATURE_TOUR,
)

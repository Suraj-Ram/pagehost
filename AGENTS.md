# pagehost

## Git

Agents have full control of ordinary git operations in this repository. Commit without waiting to be asked unless in the current agent session the human asks you to not commit. In this case the human wants control over what gets committed.

After a tangible, testable part of the system is built, make one small atomic commit for that part.

- The slice has a clear boundary and its tests pass.
- A commit contains one part. Leave unrelated work for its own commit.
- Name the commit for why the slice exists.
- Force push, hard reset, and skipping hooks still require an explicit request.
- When the human asks for a new branch, commit the work on that branch and stop. They review the branch before it is merged into `main`. Do not merge it yourself.

## Implementation plan

The task list and DAG are in `IMPLEMENTATION.md`. When you finish a task, mark its checkbox only after its exit command passes, and append the commit hash. Mark only the task you own.

The MVP gate is build-kit scenarios 01–18 and 20. Scenario 19 stays a strict expected failure. Auth enforcement, §12 components, REST, a custom CLI, and nginx are out of scope until the human asks.

This checkout on `main` is the primary repo. The only other worktree is `/Users/suraj/dev/pagehost-agent-harness` on `task/agent-harness`. Do not merge that branch unless the human asks.

## Running

`docs.md` is how to start the server and view pages. The process entry is `fastmcp run`, which loads the `server` factory in `server.py` via `fastmcp.json`. `create_server` in `pagehost/bootstrap.py` returns the FastMCP server. Tests that need an ASGI app call `.http_app()`. Do not wrap that server in an empty FastAPI app, and do not copy the adapter wiring into a one-off script.

Published HTML is under `data/sites/<id>/current/index.html`, and `data/` is gitignored. The stylesheet link is `/_assets/pagehost.css`, so opening the file with `file://` does not load it. Serve `data/sites` with the Python server in `docs.md`. Nginx replaces that server later.

## What an agent may author

Agents pass Markdown only. The spec and the build kit do not accept HTML as an input format. Raw HTML in a Markdown body is shown as text. Do not add an HTML format unless the human asks.

`replace_text` takes a short unique `old` phrase. It is the locator, and it must occur once. Rewriting a block uses `replace_section`, which does not quote the old text.

## Build kit

The scenarios and the harness are normative. The only build-kit file that may change is `pagehost-build-kit/tests/e2e/conftest.py`, and only when the process entry point changes.

```bash
uv run --with 'pytest>=9' pytest pagehost-build-kit/tests/e2e
uv run --with 'pytest>=9' python scripts/mutation_check.py
```

Scenario 19 must still be an expected failure. Run the mutation check after a change to behavior a scenario pins.

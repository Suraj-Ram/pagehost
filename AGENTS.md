# pagehost

## Git

Agents have full control of ordinary git operations in this repository. Commit without waiting to be asked unless in the current agent session the human asks you to not commit. In this case the human wants control over what gets committed.

After a tangible, testable part of the system is built, make one small atomic commit for that part.

- The slice has a clear boundary and its tests pass.
- A commit contains one part. Leave unrelated work for its own commit.
- Name the commit for why the slice exists.
- Force push, hard reset, and skipping hooks still require an explicit request.

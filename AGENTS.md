# pagehost

## Git

Agents have full control of ordinary git operations in this repository. Commit without waiting to be asked.

After a tangible, testable part of the system is built, make one small atomic commit for that part.

- The slice has a clear boundary and its tests pass.
- A commit contains one part. Leave unrelated work for its own commit.
- Name the commit for why the slice exists.
- Force push, hard reset, and skipping hooks still require an explicit request.

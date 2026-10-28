# pagehost build kit

Everything needed to build the system, in the order to use it.

| Read/use | File | What it is |
|---|---|---|
| 1 | `SPEC.md` | **The specification.** Behaviour, the 11 MCP tools, algorithms, HTML contract, security, acceptance. Start here |
| 2 | `pagehost.css` | The finished stylesheet. Serve it **unmodified** at `/_assets/pagehost.css`. Do not write CSS |
| 3 | `tests/e2e/scenarios/*.yaml` | **20 end-to-end cases**: each is a list of tool calls plus the page they must produce. These are the acceptance tests and they win over prose. `19-…` is `planned` (expected to fail until SPEC §12 is built) |
| 4 | `rendered-pages/*.html` | The real page each scenario produces, stylesheet inlined so each opens standalone. `index.html` lists them with their tool calls. Match them *semantically*, not byte for byte |
| 5 | `tests/e2e/harness/`, `conftest.py`, `test_scenarios.py`, `README.md` | The scenario runner. Implementation-blind except `conftest.py` (how to boot your server) |
| ref | `reference/` | `semantic-css.md` (stylesheet docs and component markup), `showcase.html` (every component rendered), `showcase-fragment.html` (their markup), `openapi.json` (the REST contract in machine form) |

## Running the scenarios

```
pip install pytest httpx pyyaml fastmcp uvicorn
# pytest must see tests/ on its path:   [tool.pytest.ini_options] pythonpath = ["tests"]

# against any running deployment (works for every implementation):
PAGEHOST_E2E_MCP_URL=http://localhost:8080/mcp/ PAGEHOST_E2E_TOKEN=... \
PAGEHOST_E2E_PAGE_ORIGIN=http://localhost:8080 \   # optional: reach <id>.pages... through one origin + Host header
  pytest tests/e2e
```

`tests/e2e/conftest.py` also has a *local* mode that boots the reference implementation
(`from pagehost.bootstrap import create_app` ...). It is the only implementation-aware file: adapt it to your own
entry point, or just use the remote mode above. If you use the local mode, keep the served layout in SPEC §9.2
(`<sites>/<id>/current/index.html`).

If you are not given the harness, SPEC Appendix H specifies the scenario format, matchers and snapshot rules
precisely enough to write a runner.

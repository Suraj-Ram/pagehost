# Run pagehost

Two processes. The MCP server publishes pages. A static server lets you read them. The static server is a stand-in for nginx.

## MCP

From the repo root:

```bash
PAGEHOST_TOKEN=dev-token uv run fastmcp run
```

`fastmcp.json` binds that to `127.0.0.1:8080`. Agents connect to `http://127.0.0.1:8080/mcp`. The token is required to start and is not checked on requests.

Cursor MCP config:

```json
{
  "mcpServers": {
    "pagehost": {
      "url": "http://127.0.0.1:8080/mcp"
    }
  }
}
```

| Variable | Default |
|---|---|
| `PAGEHOST_TOKEN` | required |
| `PAGEHOST_DATA_DIR` | `./data` |
| `PAGEHOST_URL_TEMPLATE` | `https://{id}.pages.internal.example.com/` |

A publish writes `data/sites/<id>/current/index.html`. `current` is a symlink to `v1`, `v2`, and so on. The stylesheet is `data/sites/_assets/pagehost.css`. Source and history are in `data/pagehost.sqlite`.

## Pages

The HTML links the stylesheet as `/_assets/pagehost.css`, so the server root has to be `data/sites`. Opening the file directly in a browser does not load the stylesheet.

```bash
python3 -m http.server 8090 --directory data/sites --bind 127.0.0.1
```

A page is then `http://127.0.0.1:8090/<id>/current/index.html`.

Nginx will replace this process. It serves each page from `<sites>/<id>/current/` and aliases `/_assets/` to `<sites>/_assets/`.

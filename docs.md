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
| `PAGEHOST_BASE_URL` | unset |
| `PAGEHOST_URL_TEMPLATE` | `https://{id}.pages.internal.example.com/` |

`PAGEHOST_BASE_URL` is the public origin pages are served from, such as `https://pages.example.com` or `http://localhost:8090`. Page links are then `<base>/p/<id>/`. Set it or `PAGEHOST_URL_TEMPLATE`, not both. Leave it unset for the local process above; that process keeps the subdomain template.

A publish writes `data/sites/<id>/current/index.html`. `current` is a symlink to `v1`, `v2`, and so on. The stylesheet is `data/sites/_assets/pagehost.css`. Source and history are in `data/pagehost.sqlite`.

## Pages

The HTML links the stylesheet as `/_assets/pagehost.css`, so the server root has to be `data/sites`. Opening the file directly in a browser does not load the stylesheet.

```bash
python3 -m http.server 8090 --directory data/sites --bind 127.0.0.1
```

A page is then `http://127.0.0.1:8090/<id>/current/index.html`.

## Docker

`compose.yaml` runs the MCP server and nginx. The app container publishes MCP on a host port. Nginx mounts the sites volume read-only and serves pages. It does not proxy MCP.

```bash
PAGEHOST_TOKEN=dev-token docker compose up --build
```

| Variable | Compose default |
|---|---|
| `PAGEHOST_TOKEN` | required |
| `PAGEHOST_MCP_PORT` | `8080` (host port forwarded to the app container) |
| `PAGEHOST_PORT` | `8090` (host port forwarded to nginx) |
| `PAGEHOST_BASE_URL` | `http://localhost:8090` |

MCP is `http://127.0.0.1:8080/mcp`, the same URL as the local process. A page is `http://localhost:8090/p/<id>/` and the stylesheet is `http://localhost:8090/_assets/pagehost.css`. `PAGEHOST_BASE_URL` has to be the origin nginx is reached at, including `PAGEHOST_PORT` when that is not 8090.

```json
{
  "mcpServers": {
    "pagehost": {
      "url": "http://127.0.0.1:8080/mcp"
    }
  }
}
```

Data stays in the compose volumes (`/data` in the app container), separate from a local `./data` directory.

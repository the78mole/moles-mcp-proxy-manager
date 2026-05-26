# moles-mcp-proxy-manager

Unified management UI, runner, and reverse proxy for MCP and OpenAPI servers.

## How it works

Each MCP server is registered with a **URL slug** (e.g., `vnbdigital`, `filesystem`).  
The manager runs on a single fixed port (default `8000`) and exposes every tool via a path-based gateway:

```
GET  /v1/mcp/{slug}/openapi.json  → served by that tool
POST /v1/mcp/{slug}/...           → proxied to that tool
```

Open WebUI only ever needs to know **one hostname and port** — no per-tool port mapping required.

## Features

- Register MCP servers from `PyPI`, `GitHub`, or `Local Path` sources.
- Register `Native OpenAPI` upstream services.
- Lifecycle controls: create, edit, delete, start, stop, update, logs.
- Single-port reverse-proxy gateway: `GET|POST|… /v1/mcp/{slug}/{path}`.
- Source-specific update behavior through `POST /api/v1/servers/{id}/update`.

## Backend (FastAPI + SQLite)

### Install dependencies

```bash
uv sync --group dev
```

### Run backend

```bash
uv run uvicorn app.main:app --reload
```

Backend API base URL: `http://localhost:8000/api/v1`

## Frontend (Vue 3 + Vite + TypeScript + Tailwind)

```bash
cd frontend
npm install
npm run dev
```

Frontend dev URL: `http://localhost:5173` (proxies `/api` and `/v1` to backend).

## API Endpoints

Management API:

- `GET  /api/v1/servers`
- `POST /api/v1/servers`
- `PUT  /api/v1/servers/{id}`
- `DELETE /api/v1/servers/{id}`
- `POST /api/v1/servers/{id}/start`
- `POST /api/v1/servers/{id}/stop`
- `POST /api/v1/servers/{id}/update`
- `GET  /api/v1/servers/{id}/logs`

Gateway (all HTTP methods):

- `{METHOD} /v1/mcp/{slug}/{path}` — reverse-proxy to the registered tool

## Update Lifecycle

- **PyPI**: stop process, run `uvx --refresh mcpo -- uvx --refresh {package_name}`, restart.
- **GitHub**: stop process, run `uvx --refresh mcpo -- uvx --refresh --from git+{git_url} {executable_name}`, restart.
- **Local Path**: stop process, run `uvx --refresh mcpo -- uvx --refresh --from {local_path} {executable_name}`, restart.
- **Native OpenAPI**: run a health check against `backend_url` and update status metadata.

---

## Deployment & Networking Guide

The manager uses a **single-port gateway** design: all registered tools are reachable through
`http://<manager-host>:8000/v1/mcp/{slug}/…`. You only ever expose **one port** on the host,
regardless of how many MCP tools are running internally.

Example Open WebUI tool URLs when three servers are registered:

```
http://moles-mcp-proxy-manager:8000/v1/mcp/vnbdigital/openapi.json
http://moles-mcp-proxy-manager:8000/v1/mcp/filesystem/openapi.json
http://moles-mcp-proxy-manager:8000/v1/mcp/weather/openapi.json
```

---

### Scenario A: Shared Docker Compose Stack (Recommended)

Place both containers in the same Compose file. Docker assigns them a shared internal network
automatically — no host port exposure is needed for the MCP gateway.

```yaml
# docker-compose.yml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    ports:
      - "3000:8080"          # expose only the UI to the host
    environment:
      - WEBUI_SECRET_KEY=change-me
    depends_on:
      - moles-mcp-proxy-manager

  moles-mcp-proxy-manager:
    image: ghcr.io/the78mole/moles-mcp-proxy-manager:latest
    ports:
      - "8000:8000"          # single port for the entire gateway
    environment:
      - MANAGER_HOST=0.0.0.0
      - MANAGER_PORT=8000
```

Start the stack:

```bash
docker compose up -d
```

In Open WebUI, register tools using the container name as the host:

```
http://moles-mcp-proxy-manager:8000/v1/mcp/vnbdigital/openapi.json
http://moles-mcp-proxy-manager:8000/v1/mcp/filesystem/openapi.json
```

---

### Scenario B: Separate Containers via Shared Bridge Network

For independently managed containers, connect them to a named bridge network so they can still
reach each other without exposing internal ports to the host.

**Step 1 — Create the shared network (once):**

```bash
docker network create ai-network
```

**Step 2 — Start each container on that network:**

```bash
# manager
docker run -d \
  --name moles-mcp-proxy-manager \
  --network ai-network \
  -p 8000:8000 \
  ghcr.io/the78mole/moles-mcp-proxy-manager:latest

# Open WebUI
docker run -d \
  --name open-webui \
  --network ai-network \
  -p 3000:8080 \
  ghcr.io/open-webui/open-webui:main
```

Open WebUI reaches all tools through:

```
http://moles-mcp-proxy-manager:8000/v1/mcp/{slug}/openapi.json
```

---

### Scenario C: Host Network Mode (Linux Only)

Bind the manager directly to the host network interface. Useful when non-Docker clients (IDE
plugins, CLI agents, native Open WebUI) also need to reach the MCP servers.

**Using `docker run`:**

```bash
docker run -d \
  --name moles-mcp-proxy-manager \
  --network host \
  ghcr.io/the78mole/moles-mcp-proxy-manager:latest
```

**Using Docker Compose:**

```yaml
services:
  moles-mcp-proxy-manager:
    image: ghcr.io/the78mole/moles-mcp-proxy-manager:latest
    network_mode: "host"
```

Every registered tool is immediately accessible on the host:

```
http://localhost:8000/v1/mcp/vnbdigital/openapi.json
http://<server-ip>:8000/v1/mcp/filesystem/openapi.json
```

> `--network host` is supported on Linux only; on macOS/Windows it has no effect.

---

### Deployment Scenarios Summary

| Scenario | Host Ports Exposed | Open WebUI Tool URL pattern |
|---|---|---|
| **A — Shared Compose Stack** | `8000` only | `http://moles-mcp-proxy-manager:8000/v1/mcp/{slug}/openapi.json` |
| **B — Shared Bridge Network** | `8000` only | `http://moles-mcp-proxy-manager:8000/v1/mcp/{slug}/openapi.json` |
| **C — Host Network (Linux)** | `8000` on host | `http://localhost:8000/v1/mcp/{slug}/openapi.json` |

In all scenarios you expose exactly **one** port and use path-based routing to reach any number of tools.

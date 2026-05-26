# moles-mcp-proxy-manager

Unified management UI, runner, and reverse proxy for MCP and OpenAPI servers.

## Features

- Register MCP servers from `PyPI`, `GitHub`, or `Local Path` sources.
- Register `Native OpenAPI` upstream services.
- Lifecycle controls: create, edit, delete, start, stop, update, logs.
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

Frontend dev URL: `http://localhost:5173` (proxies `/api` to backend).

## API Endpoints

- `GET /api/v1/servers`
- `POST /api/v1/servers`
- `PUT /api/v1/servers/{id}`
- `DELETE /api/v1/servers/{id}`
- `POST /api/v1/servers/{id}/start`
- `POST /api/v1/servers/{id}/stop`
- `POST /api/v1/servers/{id}/update`
- `GET /api/v1/servers/{id}/logs`

## Update Lifecycle

- **PyPI**: stop process, run `uvx --refresh mcpo -- uvx --refresh {package_name}`, restart.
- **GitHub**: stop process, run `uvx --refresh mcpo -- uvx --refresh --from git+{git_url} {executable_name}`, restart.
- **Local Path**: stop process, run `uvx --refresh mcpo -- uvx --refresh --from {local_path} {executable_name}`, restart.
- **Native OpenAPI**: run a health check against `backend_url` and update status metadata.

---

## Deployment & Networking Guide

This section explains how to run `moles-mcp-proxy-manager` in Docker and how to configure networking so that Open WebUI can dynamically access the MCP/OpenAPI ports it manages.

> **Key insight:** The manager may spawn MCP servers on arbitrary ports at runtime. The cleanest solutions (Scenario A and B) keep all MCP traffic on an internal Docker network, eliminating port conflicts on the host entirely. Scenario C is available when non-Docker clients also need direct access to those ports.

---

### Scenario A: Shared Docker Compose Stack (Recommended)

This is the cleanest approach. Both `open-webui` and `moles-mcp-proxy-manager` are defined in the same Compose file, so Docker automatically places them on a shared internal network. No individual MCP ports need to be published to the host machine.

```yaml
# docker-compose.yml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    ports:
      - "3000:8080"          # expose only the UI port to the host
    environment:
      - WEBUI_SECRET_KEY=change-me
    depends_on:
      - moles-mcp-proxy-manager

  moles-mcp-proxy-manager:
    image: ghcr.io/the78mole/moles-mcp-proxy-manager:latest
    # No host port bindings required — all MCP ports stay internal
    environment:
      - MANAGER_HOST=0.0.0.0
      - MANAGER_PORT=8000
```

Start the stack:

```bash
docker compose up -d
```

When registering a managed server in Open WebUI, use the **container name** as the hostname:

```
http://moles-mcp-proxy-manager:8000/openapi.json
```

Because both containers share the same Compose network, Open WebUI reaches the manager — and every MCP port it binds — without any firewall rules or host-port exposure.

---

### Scenario B: Separate Containers via Shared Bridge Network

Use this approach when your containers are managed independently (e.g., different Compose files or plain `docker run` commands) but you still want to avoid exposing internal MCP ports to the host.

**Step 1 — Create an external bridge network (once):**

```bash
docker network create ai-network
```

**Step 2 — Start each container on that network:**

```bash
# moles-mcp-proxy-manager
docker run -d \
  --name moles-mcp-proxy-manager \
  --network ai-network \
  ghcr.io/the78mole/moles-mcp-proxy-manager:latest

# Open WebUI
docker run -d \
  --name open-webui \
  --network ai-network \
  -p 3000:8080 \
  ghcr.io/open-webui/open-webui:main
```

Open WebUI can reach the manager via:

```
http://moles-mcp-proxy-manager:8000
```

All dynamically opened MCP ports remain inside the `ai-network` bridge and are never published to the host. This avoids port conflicts while preserving full container isolation between unrelated stacks.

---

### Scenario C: Host Network Mode (Linux Only)

Host network mode binds the manager directly to the host's network interface, bypassing Docker's network isolation. Every port opened by the manager — including dynamically spawned MCP server ports — is immediately reachable on the host.

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

Any MCP server spawned on port `N` is immediately accessible at:

```
http://localhost:N
http://<server-ip>:N
```

This is ideal when non-Docker applications (e.g., a locally running IDE plugin, CLI agent, or native Open WebUI) also need direct access to the MCP servers. Note that `--network host` is only supported on Linux; on macOS and Windows it has no effect.

---

### Open WebUI Integration Summary

| Deployment Scenario | Host Ports Exposed? | Open WebUI Target URL |
|---|---|---|
| **A — Shared Compose Stack** | No (UI only) | `http://moles-mcp-proxy-manager:<PORT>` |
| **B — Shared Bridge Network** | No (UI only) | `http://moles-mcp-proxy-manager:<PORT>` |
| **C — Host Network (Linux)** | Yes (all ports) | `http://localhost:<PORT>` or `http://<server-ip>:<PORT>` |

> Replace `<PORT>` with the manager API port (default `8000`) or any specific MCP server port registered through the manager.

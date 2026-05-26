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

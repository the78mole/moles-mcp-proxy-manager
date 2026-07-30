import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Server, SourceType
from app.process_manager import manager
from app.schemas import LogResponse, ServerCreate, ServerOut, ServerUpdate

# Headers that must not be forwarded when proxying (hop-by-hop).
_HOP_BY_HOP = frozenset(
    [
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
    ]
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Migrate: add args column if missing (for existing databases)
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(servers)"))}
        if "args" not in cols:
            conn.execute(text('ALTER TABLE servers ADD COLUMN args TEXT NOT NULL DEFAULT "[]"'))
            conn.commit()
    yield


app = FastAPI(title="moles-mcp-proxy-manager", lifespan=lifespan, redirect_slashes=False)

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def serve_index() -> Response:
        return Response(
            content=(_FRONTEND_DIST / "index.html").read_bytes(),
            media_type="text/html",
        )
else:
    @app.get("/", include_in_schema=False)
    def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs")


def validate_source(payload: ServerCreate | ServerUpdate, source_type: SourceType) -> None:
    if source_type == SourceType.PYPI and not payload.package_name:
        raise HTTPException(status_code=400, detail="PyPI source requires package_name")
    if source_type in {SourceType.GITHUB, SourceType.LOCAL} and not payload.executable_name:
        raise HTTPException(status_code=400, detail="Executable name is required")
    if source_type == SourceType.GITHUB and not payload.git_url:
        raise HTTPException(status_code=400, detail="GitHub source requires git_url")
    if source_type == SourceType.LOCAL and not payload.local_path:
        raise HTTPException(status_code=400, detail="Local source requires local_path")
    if source_type == SourceType.OPENAPI and not payload.backend_url:
        raise HTTPException(status_code=400, detail="OpenAPI source requires backend_url")
    if source_type == SourceType.NPM and not payload.package_name:
        raise HTTPException(status_code=400, detail="NPM source requires package_name")


def to_server_out(server: Server) -> ServerOut:
    return ServerOut(
        id=server.id,
        name=server.name,
        slug=server.slug,
        source_type=SourceType(server.source_type),
        package_name=server.package_name,
        executable_name=server.executable_name,
        git_url=server.git_url,
        local_path=server.local_path,
        backend_url=server.backend_url,
        env_vars=json.loads(server.env_vars),
        args=json.loads(server.args),
        status=server.status,
        internal_port=manager.get_internal_port(server.id),
        last_health_status=server.last_health_status,
    )


# ── CRUD ─────────────────────────────────────────────────────────────────────

@app.get("/api/v1/servers", response_model=list[ServerOut])
def list_servers(db: Session = Depends(get_db)) -> list[ServerOut]:
    return [to_server_out(server) for server in db.query(Server).order_by(Server.id.asc()).all()]


@app.post("/api/v1/servers", response_model=ServerOut)
def create_server(payload: ServerCreate, db: Session = Depends(get_db)) -> ServerOut:
    validate_source(payload, payload.source_type)
    server = Server(
        name=payload.name,
        slug=payload.slug,
        source_type=payload.source_type.value,
        package_name=payload.package_name,
        executable_name=payload.executable_name,
        git_url=str(payload.git_url) if payload.git_url else None,
        local_path=payload.local_path,
        backend_url=str(payload.backend_url) if payload.backend_url else None,
        env_vars=json.dumps(payload.env_vars),
        args=json.dumps(payload.args),
        status="stopped",
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    return to_server_out(server)


@app.put("/api/v1/servers/{server_id}", response_model=ServerOut)
def put_server(server_id: int, payload: ServerUpdate, db: Session = Depends(get_db)) -> ServerOut:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    data = payload.model_dump(exclude_unset=True)
    source_type = SourceType(server.source_type)

    if "name" in data:
        server.name = data["name"]
    if "slug" in data:
        server.slug = data["slug"]
    if "package_name" in data:
        server.package_name = data["package_name"]
    if "executable_name" in data:
        server.executable_name = data["executable_name"]
    if "git_url" in data:
        server.git_url = str(data["git_url"]) if data["git_url"] else None
    if "local_path" in data:
        server.local_path = data["local_path"]
    if "backend_url" in data:
        server.backend_url = str(data["backend_url"]) if data["backend_url"] else None
    if "env_vars" in data:
        server.env_vars = json.dumps(data["env_vars"])
    if "args" in data:
        server.args = json.dumps(data["args"])

    effective_payload = ServerCreate(
        name=server.name,
        slug=server.slug,
        source_type=source_type,
        package_name=server.package_name,
        executable_name=server.executable_name,
        git_url=server.git_url,
        local_path=server.local_path,
        backend_url=server.backend_url,
        env_vars=json.loads(server.env_vars),
        args=json.loads(server.args),
    )
    validate_source(effective_payload, source_type)
    db.commit()
    db.refresh(server)
    return to_server_out(server)


@app.delete("/api/v1/servers/{server_id}")
async def delete_server(server_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    await manager.stop_server(server_id)
    db.delete(server)
    db.commit()
    return {"status": "deleted"}


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.post("/api/v1/servers/{server_id}/start", response_model=ServerOut)
async def start_server(server_id: int, db: Session = Depends(get_db)) -> ServerOut:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    await manager.start_server(server)
    server.status = "running"
    db.commit()
    db.refresh(server)
    return to_server_out(server)


@app.post("/api/v1/servers/{server_id}/stop", response_model=ServerOut)
async def stop_server(server_id: int, db: Session = Depends(get_db)) -> ServerOut:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    await manager.stop_server(server_id)
    server.status = "stopped"
    db.commit()
    db.refresh(server)
    return to_server_out(server)


@app.post("/api/v1/servers/{server_id}/update", response_model=ServerOut)
async def refresh_server(server_id: int, db: Session = Depends(get_db)) -> ServerOut:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    update_status = await manager.update_server(server)
    if SourceType(server.source_type) == SourceType.OPENAPI:
        server.last_health_status = update_status
    else:
        server.status = "running"
    db.commit()
    db.refresh(server)
    return to_server_out(server)


@app.get("/api/v1/servers/{server_id}/logs", response_model=LogResponse)
def get_server_logs(server_id: int, db: Session = Depends(get_db)) -> LogResponse:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return LogResponse(logs=manager.get_logs(server_id))


@app.get("/api/v1/logs")
def get_all_logs(db: Session = Depends(get_db)):
    """Aggregated logs for all servers, ordered by server."""
    srv_list = db.query(Server).order_by(Server.id).all()
    return [
        {"id": srv.id, "slug": srv.slug, "name": srv.name, "lines": manager.get_logs(srv.id)}
        for srv in srv_list
    ]


@app.websocket("/api/v1/ws/logs")
async def ws_logs(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    """Stream log lines from all MCP servers over WebSocket."""
    await websocket.accept()
    srv_list = db.query(Server).order_by(Server.id).all()
    slug_map = {srv.id: srv.slug for srv in srv_list}
    # Replay existing history first
    for srv in srv_list:
        for line in manager.get_logs(srv.id):
            await websocket.send_json({"slug": slug_map[srv.id], "line": line})
    # Stream new lines as they arrive
    q = manager.subscribe_logs()
    try:
        while True:
            try:
                msg: dict = await asyncio.wait_for(q.get(), timeout=20.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"ping": True})
                continue
            slug = slug_map.get(msg["id"], f"srv-{msg['id']}")
            await websocket.send_json({"slug": slug, "line": msg["line"]})
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe_logs(q)


# ── MCP JSON-RPC helpers (Streamable HTTP Transport) ─────────────────────────

def _jsonrpc_response(rpc_id: int | str | None, result: dict) -> Response:
    return Response(
        content=json.dumps({"jsonrpc": "2.0", "id": rpc_id, "result": result}),
        media_type="application/json",
    )


def _jsonrpc_error_response(rpc_id: int | str | None, code: int, message: str) -> Response:
    return Response(
        content=json.dumps(
            {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}
        ),
        media_type="application/json",
    )


def _openapi_to_mcp_tools(openapi: dict) -> list[dict]:
    """Convert an mcpo OpenAPI schema into an MCP tools/list result."""
    tools: list[dict] = []
    components = openapi.get("components", {}).get("schemas", {})
    for path, methods in openapi.get("paths", {}).items():
        tool_name = path.lstrip("/")
        for _method, op in methods.items():
            description = op.get("description") or op.get("summary") or tool_name
            input_schema: dict = {"type": "object", "properties": {}, "required": []}
            rb = op.get("requestBody", {})
            if rb:
                json_schema = (
                    rb.get("content", {}).get("application/json", {}).get("schema", {})
                )
                if "$ref" in json_schema:
                    ref_name = json_schema["$ref"].rsplit("/", 1)[-1]
                    json_schema = components.get(ref_name, input_schema)
                if json_schema:
                    input_schema = json_schema
            tools.append(
                {"name": tool_name, "description": description, "inputSchema": input_schema}
            )
            break  # one method per path is enough
    return tools


# ── MCP Streamable HTTP endpoint (VS Code / MCP clients) ─────────────────────

@app.post("/v1/mcp/{server_slug}")
async def mcp_jsonrpc(
    server_slug: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """MCP Streamable HTTP transport — handles JSON-RPC 2.0 from VS Code and other MCP clients."""
    server = db.query(Server).filter(Server.slug == server_slug).first()
    if server is None:
        raise HTTPException(
            status_code=404, detail=f"No server registered with slug '{server_slug}'"
        )

    try:
        body = await request.json()
    except Exception:
        return _jsonrpc_error_response(None, -32700, "Parse error")

    # Notifications carry no "id" — acknowledge without a response body
    if "id" not in body:
        return Response(status_code=202)

    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    if method == "initialize":
        # Auto-start the backend if not yet running — fire and forget
        asyncio.create_task(manager.start_server(server))
        return _jsonrpc_response(
            rpc_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": server.name, "version": "1.0.0"},
            },
        )

    if method == "ping":
        return _jsonrpc_response(rpc_id, {})

    # All further methods need the backend to be reachable — resolve base_url
    source_type = SourceType(server.source_type)
    if source_type == SourceType.OPENAPI:
        if not server.backend_url:
            return _jsonrpc_error_response(rpc_id, -32000, "OpenAPI backend_url not configured")
        base_url = server.backend_url.rstrip("/")
    else:
        # Wait up to 30 s for mcpo to actually accept HTTP connections (not just port assigned)
        base_url = None
        for _ in range(30):
            internal_port = manager.get_internal_port(server.id)
            if internal_port is not None:
                try:
                    async with httpx.AsyncClient(timeout=1) as probe:
                        await probe.get(f"http://127.0.0.1:{internal_port}/openapi.json")
                    base_url = f"http://127.0.0.1:{internal_port}"
                    break
                except (httpx.ConnectError, httpx.TimeoutException):
                    pass
            await asyncio.sleep(1)
        if base_url is None:
            return _jsonrpc_error_response(
                rpc_id, -32000, f"Server '{server_slug}' did not start in time"
            )

    if method == "tools/list":
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base_url}/openapi.json")
        if resp.status_code != 200:
            return _jsonrpc_error_response(
                rpc_id, -32000, f"Failed to fetch tool list: HTTP {resp.status_code}"
            )
        return _jsonrpc_response(rpc_id, {"tools": _openapi_to_mcp_tools(resp.json())})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{base_url}/{tool_name}", json=arguments)
        if resp.status_code >= 400:
            return _jsonrpc_response(
                rpc_id,
                {"content": [{"type": "text", "text": resp.text}], "isError": True},
            )
        return _jsonrpc_response(
            rpc_id, {"content": [{"type": "text", "text": resp.text}]}
        )

    return _jsonrpc_error_response(rpc_id, -32601, f"Method not found: {method}")


# ── Reverse-proxy gateway ─────────────────────────────────────────────────────

@app.api_route(
    "/v1/mcp/{server_slug}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_mcp(
    server_slug: str,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    server = db.query(Server).filter(Server.slug == server_slug).first()
    if server is None:
        raise HTTPException(status_code=404, detail=f"No server registered with slug '{server_slug}'")

    source_type = SourceType(server.source_type)

    if source_type == SourceType.OPENAPI:
        if not server.backend_url:
            raise HTTPException(status_code=503, detail="OpenAPI backend_url not configured")
        base = server.backend_url.rstrip("/")
        target_url = f"{base}/{path}" if path else base
    else:
        internal_port = manager.get_internal_port(server.id)
        if internal_port is None:
            raise HTTPException(
                status_code=503,
                detail=f"Server '{server_slug}' is not running. Start it first.",
            )
        target_url = f"http://127.0.0.1:{internal_port}/{path}"

    # Preserve query string
    qs = request.url.query
    if qs:
        target_url = f"{target_url}?{qs}"

    # Forward headers, dropping hop-by-hop
    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP
    }

    body = await request.body()

    async with httpx.AsyncClient(timeout=60) as client:
        upstream = await client.request(
            method=request.method,
            url=target_url,
            headers=forward_headers,
            content=body,
        )

    # Filter response headers as well
    response_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP
    }

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


if __name__ == "__main__":
    import logging
    import os
    import socket

    import uvicorn

    _host = os.environ.get("MANAGER_HOST", "0.0.0.0")
    _port = int(os.environ.get("MANAGER_PORT", "8001"))

    # Resolve a human-readable local IP for the startup banner
    try:
        _local_ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        _local_ip = "127.0.0.1"

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
    _log = logging.getLogger(__name__)
    _log.info("Starting moles-mcp-proxy-manager")
    _log.info("Management API  →  http://localhost:%d/api/v1/servers", _port)
    _log.info("MCP Gateway     →  http://localhost:%d/v1/mcp/{slug}/...", _port)
    _log.info("OpenAPI docs    →  http://localhost:%d/docs", _port)
    if _host == "0.0.0.0" and _local_ip != "127.0.0.1":
        _log.info("Network access  →  http://%s:%d", _local_ip, _port)

    uvicorn.run(
        "app.main:app",
        host=_host,
        port=_port,
    )

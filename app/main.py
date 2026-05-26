import json
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
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
    yield


app = FastAPI(title="moles-mcp-proxy-manager", lifespan=lifespan)


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

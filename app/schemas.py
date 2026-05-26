from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models import SourceType


class ServerBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: SourceType
    package_name: str | None = None
    executable_name: str | None = None
    git_url: HttpUrl | None = None
    local_path: str | None = None
    backend_url: HttpUrl | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)
    target_port: int = Field(ge=1, le=65535)


class ServerCreate(ServerBase):
    pass


class ServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    package_name: str | None = None
    executable_name: str | None = None
    git_url: HttpUrl | None = None
    local_path: str | None = None
    backend_url: HttpUrl | None = None
    env_vars: dict[str, str] | None = None
    target_port: int | None = Field(default=None, ge=1, le=65535)


class ServerOut(ServerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    last_health_status: str | None = None


class LogResponse(BaseModel):
    logs: list[str]

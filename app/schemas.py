import re

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models import SourceType

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ServerBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100)
    source_type: SourceType
    package_name: str | None = None
    executable_name: str | None = None
    git_url: HttpUrl | None = None
    local_path: str | None = None
    backend_url: HttpUrl | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)
    args: list[str] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def slug_must_be_url_safe(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("slug must be lowercase alphanumeric with optional hyphens (e.g. 'my-tool')")
        return v


class ServerCreate(ServerBase):
    pass


class ServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    package_name: str | None = None
    executable_name: str | None = None
    git_url: HttpUrl | None = None
    local_path: str | None = None
    backend_url: HttpUrl | None = None
    env_vars: dict[str, str] | None = None
    args: list[str] | None = None

    @field_validator("slug")
    @classmethod
    def slug_must_be_url_safe(cls, v: str | None) -> str | None:
        if v is not None and not _SLUG_RE.match(v):
            raise ValueError("slug must be lowercase alphanumeric with optional hyphens (e.g. 'my-tool')")
        return v


class ServerOut(ServerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    internal_port: int | None = None
    last_health_status: str | None = None


class LogResponse(BaseModel):
    logs: list[str]

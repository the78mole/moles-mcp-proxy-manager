from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SourceType(StrEnum):
    PYPI = "PYPI"
    GITHUB = "GITHUB"
    LOCAL = "LOCAL"
    OPENAPI = "OPENAPI"
    NPM = "NPM"


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    package_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    executable_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    git_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    backend_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    env_vars: Mapped[str] = mapped_column(Text, default="{}", server_default="{}", nullable=False)
    args: Mapped[str] = mapped_column(Text, default="[]", server_default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="stopped", nullable=False)
    last_health_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

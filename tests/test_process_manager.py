from types import SimpleNamespace

from app.models import SourceType
from app.process_manager import ProcessManager


def _server(**kwargs):
    defaults = {
        "id": 1,
        "source_type": SourceType.PYPI,
        "package_name": "vnbdigital-mcp",
        "executable_name": "vnbdigital-mcp",
        "git_url": "https://github.com/the78mole/vnbdigital-mcp",
        "local_path": "/tmp/local-mcp",
        "target_port": 9000,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_build_run_command_pypi() -> None:
    server = _server(source_type=SourceType.PYPI)
    assert ProcessManager.build_run_command(server) == [
        "uvx",
        "mcpo",
        "--port",
        "9000",
        "--",
        "uvx",
        "vnbdigital-mcp",
    ]


def test_build_run_command_github() -> None:
    server = _server(source_type=SourceType.GITHUB)
    assert ProcessManager.build_run_command(server) == [
        "uvx",
        "mcpo",
        "--port",
        "9000",
        "--",
        "uvx",
        "--from",
        "git+https://github.com/the78mole/vnbdigital-mcp",
        "vnbdigital-mcp",
    ]


def test_build_refresh_command_local() -> None:
    server = _server(source_type=SourceType.LOCAL)
    assert ProcessManager.build_refresh_command(server) == [
        "uvx",
        "--refresh",
        "mcpo",
        "--",
        "uvx",
        "--refresh",
        "--from",
        "/tmp/local-mcp",
        "vnbdigital-mcp",
    ]

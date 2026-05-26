import asyncio
import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Deque

import httpx

from app.models import Server, SourceType


@dataclass
class ProcessHandle:
    process: asyncio.subprocess.Process
    logs: Deque[str] = field(default_factory=lambda: deque(maxlen=500))


class ProcessManager:
    def __init__(self) -> None:
        self._processes: dict[int, ProcessHandle] = {}
        self._history: dict[int, Deque[str]] = defaultdict(lambda: deque(maxlen=500))

    async def _collect_stream(
        self,
        server_id: int,
        stream: asyncio.StreamReader | None,
        destination: Deque[str],
    ) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            destination.append(text)
            self._history[server_id].append(text)

    @staticmethod
    def _require_value(value: str | None, field_name: str) -> str:
        if not value:
            raise ValueError(f"{field_name} is required for this source type")
        return value

    @staticmethod
    def build_run_command(server: Server) -> list[str]:
        if server.source_type == SourceType.PYPI:
            package_name = ProcessManager._require_value(server.package_name, "package_name")
            return ["uvx", "mcpo", "--port", str(server.target_port), "--", "uvx", package_name]
        if server.source_type == SourceType.GITHUB:
            git_url = ProcessManager._require_value(server.git_url, "git_url")
            executable_name = ProcessManager._require_value(server.executable_name, "executable_name")
            return [
                "uvx",
                "mcpo",
                "--port",
                str(server.target_port),
                "--",
                "uvx",
                "--from",
                f"git+{git_url}",
                executable_name,
            ]
        if server.source_type == SourceType.LOCAL:
            local_path = ProcessManager._require_value(server.local_path, "local_path")
            executable_name = ProcessManager._require_value(server.executable_name, "executable_name")
            return [
                "uvx",
                "mcpo",
                "--port",
                str(server.target_port),
                "--",
                "uvx",
                "--from",
                local_path,
                executable_name,
            ]
        raise ValueError("OPENAPI servers do not support subprocess run commands")

    @staticmethod
    def build_refresh_command(server: Server) -> list[str]:
        if server.source_type == SourceType.PYPI:
            package_name = ProcessManager._require_value(server.package_name, "package_name")
            return ["uvx", "--refresh", "mcpo", "--", "uvx", "--refresh", package_name]
        if server.source_type == SourceType.GITHUB:
            git_url = ProcessManager._require_value(server.git_url, "git_url")
            executable_name = ProcessManager._require_value(server.executable_name, "executable_name")
            return [
                "uvx",
                "--refresh",
                "mcpo",
                "--",
                "uvx",
                "--refresh",
                "--from",
                f"git+{git_url}",
                executable_name,
            ]
        if server.source_type == SourceType.LOCAL:
            local_path = ProcessManager._require_value(server.local_path, "local_path")
            executable_name = ProcessManager._require_value(server.executable_name, "executable_name")
            return [
                "uvx",
                "--refresh",
                "mcpo",
                "--",
                "uvx",
                "--refresh",
                "--from",
                local_path,
                executable_name,
            ]
        raise ValueError("OPENAPI servers do not support subprocess refresh commands")

    async def start_server(self, server: Server) -> None:
        if server.source_type == SourceType.OPENAPI:
            await self.health_check(server)
            return

        if server.id in self._processes:
            return

        command = self.build_run_command(server)
        env = os.environ.copy()
        try:
            env.update(json.loads(server.env_vars))
        except JSONDecodeError as exc:
            self._history[server.id].append(f"invalid_env_vars_json: {exc}")
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        handle = ProcessHandle(process=process)
        self._processes[server.id] = handle
        asyncio.create_task(self._collect_stream(server.id, process.stdout, handle.logs))
        asyncio.create_task(self._collect_stream(server.id, process.stderr, handle.logs))

    async def stop_server(self, server_id: int, timeout_seconds: float = 5.0) -> None:
        handle = self._processes.get(server_id)
        if handle is None:
            return

        process = handle.process
        if process.returncode is not None:
            self._processes.pop(server_id, None)
            return

        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
        finally:
            self._processes.pop(server_id, None)

    async def health_check(self, server: Server) -> str:
        if not server.backend_url:
            return "unknown"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(server.backend_url)
            status = "healthy" if response.status_code < 500 else "unhealthy"
        except Exception:
            status = "unreachable"
        self._history[server.id].append(f"health_check={status}")
        return status

    async def update_server(self, server: Server) -> str:
        if server.source_type == SourceType.OPENAPI:
            return await self.health_check(server)

        await self.stop_server(server.id)
        refresh_command = self.build_refresh_command(server)
        refresh = await asyncio.create_subprocess_exec(
            *refresh_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await refresh.communicate()
        if stdout:
            self._history[server.id].append(stdout.decode(errors="replace").strip())
        if stderr:
            self._history[server.id].append(stderr.decode(errors="replace").strip())
        await self.start_server(server)
        return "updated"

    def get_logs(self, server_id: int) -> list[str]:
        active = self._processes.get(server_id)
        active_logs = list(active.logs) if active else []
        history_logs = list(self._history.get(server_id, []))
        return history_logs + active_logs


manager = ProcessManager()

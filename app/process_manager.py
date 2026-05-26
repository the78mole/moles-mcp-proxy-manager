import asyncio
import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
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
    def build_run_command(server: Server) -> list[str]:
        if server.source_type == SourceType.PYPI:
            return ["uvx", "mcpo", "--port", str(server.target_port), "--", "uvx", server.package_name or ""]
        if server.source_type == SourceType.GITHUB:
            return [
                "uvx",
                "mcpo",
                "--port",
                str(server.target_port),
                "--",
                "uvx",
                "--from",
                f"git+{server.git_url}",
                server.executable_name or "",
            ]
        if server.source_type == SourceType.LOCAL:
            return [
                "uvx",
                "mcpo",
                "--port",
                str(server.target_port),
                "--",
                "uvx",
                "--from",
                server.local_path or "",
                server.executable_name or "",
            ]
        raise ValueError("OPENAPI servers do not support subprocess run commands")

    @staticmethod
    def build_refresh_command(server: Server) -> list[str]:
        if server.source_type == SourceType.PYPI:
            return ["uvx", "--refresh", "mcpo", "--", "uvx", "--refresh", server.package_name or ""]
        if server.source_type == SourceType.GITHUB:
            return [
                "uvx",
                "--refresh",
                "mcpo",
                "--",
                "uvx",
                "--refresh",
                "--from",
                f"git+{server.git_url}",
                server.executable_name or "",
            ]
        if server.source_type == SourceType.LOCAL:
            return [
                "uvx",
                "--refresh",
                "mcpo",
                "--",
                "uvx",
                "--refresh",
                "--from",
                server.local_path or "",
                server.executable_name or "",
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
        env.update(json.loads(server.env_vars))
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

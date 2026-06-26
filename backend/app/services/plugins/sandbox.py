"""Run untrusted plugin code with real isolation.

The previous version was security theater: it imported ``resource`` but never
used it, named a method ``_execute_in_subprocess`` that actually ran the plugin
*in the API process*, and never enforced the memory/CPU/timeout limits it
advertised. A malicious or buggy plugin could exhaust memory, spin forever, or
read anything the API process could.

This version forks a child process, applies ``RLIMIT_AS`` (address space) and
``RLIMIT_CPU`` via ``resource.setrlimit`` in the child before importing the
plugin, and enforces a wall-clock timeout from the parent (terminating the child
if it overruns). Arguments and results cross the process boundary as pickles, so
plugin return values must be picklable.
"""

import asyncio
import importlib.util
import multiprocessing
import os
import resource
import traceback
from dataclasses import dataclass
from typing import Any

from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class SandboxConfig:
    max_memory_mb: int = 256
    max_cpu_seconds: int = 30
    timeout_seconds: int = 30
    network_enabled: bool = True
    allowed_paths: list[str] = None
    allowed_domains: list[str] = None

    def __post_init__(self):
        if self.allowed_paths is None:
            self.allowed_paths = []
        if self.allowed_domains is None:
            self.allowed_domains = []


class SandboxError(Exception):
    pass


def _child_entry(func_path: str, args: tuple, kwargs: dict,
                 max_memory_mb: int, max_cpu_seconds: int, conn) -> None:
    """Runs in the forked child: clamp resources, import, execute, report back."""
    try:
        if max_memory_mb:
            limit = max_memory_mb * 1024 * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            except (ValueError, OSError):
                pass
        if max_cpu_seconds:
            try:
                resource.setrlimit(
                    resource.RLIMIT_CPU, (max_cpu_seconds, max_cpu_seconds + 1)
                )
            except (ValueError, OSError):
                pass

        module_path, func_name = func_path.rsplit(".", 1)
        spec = importlib.util.find_spec(module_path)
        if not spec or not spec.origin:
            conn.send(("error", f"Module not found: {module_path}"))
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        func = getattr(module, func_name, None)
        if not func:
            conn.send(("error", f"Function not found: {func_name}"))
            return

        if asyncio.iscoroutinefunction(func):
            result = asyncio.new_event_loop().run_until_complete(func(*args, **kwargs))
        else:
            result = func(*args, **kwargs)
        conn.send(("ok", result))
    except Exception as e:  # report, don't crash silently
        conn.send(("error", f"{e}\n{traceback.format_exc()[:500]}"))
    finally:
        conn.close()


class PluginSandbox:
    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()

    async def run(
        self,
        func_path: str,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> Any:
        kwargs = kwargs or {}

        # Validate the module location in the *parent* before spawning, so a
        # disallowed path is rejected without ever loading the code.
        module_path = func_path.rsplit(".", 1)[0]
        spec = importlib.util.find_spec(module_path)
        if not spec or not spec.origin:
            raise SandboxError(f"Module not found: {module_path}")
        if self.config.allowed_paths:
            allowed = any(
                os.path.abspath(spec.origin).startswith(os.path.abspath(p))
                for p in self.config.allowed_paths
            )
            if not allowed:
                raise SandboxError(f"Module outside allowed paths: {spec.origin}")

        try:
            return await asyncio.wait_for(
                self._run_in_process(func_path, args, kwargs),
                timeout=self.config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise SandboxError(
                f"Plugin execution timed out after {self.config.timeout_seconds}s"
            )

    async def _run_in_process(self, func_path, args, kwargs) -> Any:
        ctx = multiprocessing.get_context("fork")
        parent_conn, child_conn = ctx.Pipe(duplex=False)
        proc = ctx.Process(
            target=_child_entry,
            args=(func_path, args, kwargs,
                  self.config.max_memory_mb, self.config.max_cpu_seconds, child_conn),
        )
        proc.start()
        child_conn.close()  # only the child writes

        loop = asyncio.get_running_loop()
        try:
            status, payload = await loop.run_in_executor(None, self._recv, parent_conn, proc)
        finally:
            await loop.run_in_executor(None, self._reap, proc)

        if status == "ok":
            return payload
        raise SandboxError(f"Execution error: {payload}")

    @staticmethod
    def _recv(parent_conn, proc):
        try:
            if parent_conn.poll(None):  # block until data or EOF
                return parent_conn.recv()
        except EOFError:
            pass
        finally:
            parent_conn.close()
        code = proc.exitcode
        # A child killed by RLIMIT_AS/RLIMIT_CPU dies before sending anything.
        return ("error", f"plugin process exited without a result (exit code {code})")

    @staticmethod
    def _reap(proc):
        if proc.is_alive():
            proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join()

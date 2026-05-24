import asyncio
import importlib.util
import os
import resource
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Optional

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
        try:
            result = await asyncio.wait_for(
                self._execute_in_subprocess(func_path, args, kwargs),
                timeout=self.config.timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            raise SandboxError(f"Plugin execution timed out after {self.config.timeout_seconds}s")
        except Exception as e:
            raise SandboxError(f"Plugin execution failed: {e}")

    async def _execute_in_subprocess(
        self,
        func_path: str,
        args: tuple,
        kwargs: dict,
    ) -> Any:
        module_path, func_name = func_path.rsplit(".", 1)

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

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise SandboxError(f"Module load failed: {e}")

        func = getattr(module, func_name, None)
        if not func:
            raise SandboxError(f"Function not found: {func_name}")

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("sandbox_execution_error", error=str(e), traceback=tb[:500])
            raise SandboxError(f"Execution error: {e}") from e

        return result

"""Liveness and readiness. Liveness is "the process runs", readiness checks dependencies."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

CheckFn = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class HealthReport:
    ok: bool
    checks: list[CheckResult]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.ok else "unavailable",
            "checks": {
                check.name: {"ok": check.ok} | ({"error": check.error} if check.error else {})
                for check in self.checks
            },
        }


class HealthRegistry:
    """Named readiness checks. A check passes when it returns without raising."""

    def __init__(self, timeout: float = 3.0) -> None:
        self._checks: dict[str, CheckFn] = {}
        self._timeout = timeout

    def add(self, name: str, check: CheckFn) -> None:
        self._checks[name] = check

    async def run(self) -> HealthReport:
        results = await asyncio.gather(
            *(self._run_one(name, check) for name, check in self._checks.items())
        )
        return HealthReport(ok=all(result.ok for result in results), checks=list(results))

    async def _run_one(self, name: str, check: CheckFn) -> CheckResult:
        try:
            await asyncio.wait_for(check(), timeout=self._timeout)
        except TimeoutError:
            return CheckResult(name=name, ok=False, error="timeout")
        except Exception as exc:  # a failing check must not crash the endpoint
            return CheckResult(name=name, ok=False, error=f"{type(exc).__name__}: {exc}")
        return CheckResult(name=name, ok=True)


def tcp_check(host: str, port: int) -> CheckFn:
    """Readiness check that only proves a TCP port accepts connections."""

    async def check() -> None:
        _, writer = await asyncio.open_connection(host, port)
        writer.close()
        await writer.wait_closed()

    return check

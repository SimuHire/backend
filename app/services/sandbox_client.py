from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

SandboxStatus = Literal["passed", "failed", "timeout", "error"]


class SandboxError(Exception):
    """Raised when the sandbox cannot return a usable result."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SandboxRunResult:
    """Normalized sandbox run output."""

    status: SandboxStatus
    passed: int
    failed: int
    stdout: str
    stderr: str
    total: int
    duration_ms: int | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> SandboxRunResult:
        """Normalize provider response into a consistent structure."""
        payload = data.get("result") or data
        tests = payload.get("tests") or {}

        passed = int(payload.get("passed") or tests.get("passed") or 0)
        failed = int(payload.get("failed") or tests.get("failed") or 0)
        stdout = str(payload.get("stdout") or "")
        stderr = str(payload.get("stderr") or "")
        timed_out = bool(payload.get("timeout") or tests.get("timeout"))

        status: SandboxStatus
        status_text = str(payload.get("status") or "").lower()
        if timed_out:
            status = "timeout"
        elif failed > 0:
            status = "failed"
        elif status_text in {"passed", "failed", "timeout"}:
            status = status_text  # type: ignore[assignment]
        elif stderr.strip():
            status = "failed"
        else:
            status = "passed"

        total = passed + failed
        if total == 0 and status == "passed":
            # If no explicit counts were provided but we got stdout/stderr,
            # treat it as a single logical run for display purposes.
            total = 0

        return cls(
            status=status,
            passed=passed,
            failed=failed,
            stdout=stdout,
            stderr=stderr,
            total=total,
            duration_ms=payload.get("duration_ms") or payload.get("durationMs"),
            raw=payload,
        )

    @property
    def timeout(self) -> bool:
        """Return True if the sandbox run timed out."""
        return self.status == "timeout"


class SandboxClient:
    """HTTP client for the external code execution sandbox."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        default_timeout: float = 30.0,
        poll_interval_seconds: float = 0.5,
        max_poll_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.default_timeout = default_timeout
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_seconds = max_poll_seconds
        self.transport = transport

    async def run_tests(
        self,
        *,
        task_ref: str,
        code: str | None,
        files: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> SandboxRunResult:
        """Execute code against bundled tests for a given task."""
        payload = {
            "taskRef": task_ref,
            "code": code or "",
            "files": files or {},
            "timeout": timeout_seconds or self.default_timeout,
        }
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(
            base_url=self.base_url, transport=self.transport
        ) as client:
            data = await self._start_run(
                client, payload, headers=headers, timeout_seconds=timeout_seconds
            )

            if self._is_complete(data):
                return SandboxRunResult.from_payload(data)

            run_id = data.get("runId") or data.get("id")
            poll_url = data.get("pollUrl")
            if not poll_url and run_id:
                poll_url = f"/runs/{run_id}"
            if poll_url and not poll_url.startswith(("http://", "https://", "/")):
                poll_url = f"/{poll_url}"
            if not poll_url:
                raise SandboxError("Sandbox response missing runId")

            return await self._poll_run(client, poll_url, task_ref, headers=headers)

    async def _start_run(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        try:
            resp = await client.post(
                "/run",
                json=payload,
                headers=headers,
                timeout=(timeout_seconds or self.default_timeout) + 5,
            )
        except httpx.TimeoutException as exc:  # pragma: no cover - network
            logger.warning(
                "sandbox_request_timeout",
                extra={"task_ref": payload.get("taskRef"), "timeout": timeout_seconds},
            )
            raise SandboxError("Sandbox request timed out") from exc
        except httpx.HTTPError as exc:  # pragma: no cover - network
            logger.error(
                "sandbox_request_failed",
                extra={"task_ref": payload.get("taskRef"), "error": str(exc)},
            )
            raise SandboxError("Sandbox request failed") from exc

        self._raise_on_http_error(resp, payload.get("taskRef"))

        try:
            return resp.json()
        except ValueError as exc:
            raise SandboxError("Invalid sandbox response") from exc

    async def _poll_run(
        self,
        client: httpx.AsyncClient,
        poll_url: str,
        task_ref: str,
        *,
        headers: dict[str, str],
    ) -> SandboxRunResult:
        """Poll the sandbox for completion."""
        deadline = time.monotonic() + self.max_poll_seconds
        last_payload: dict[str, Any] = {}
        while time.monotonic() < deadline:
            await asyncio.sleep(self.poll_interval_seconds)
            try:
                resp = await client.get(
                    poll_url, headers=headers, timeout=self.default_timeout + 5
                )
            except httpx.TimeoutException as exc:  # pragma: no cover - network
                logger.warning(
                    "sandbox_poll_timeout",
                    extra={"task_ref": task_ref, "poll_url": poll_url},
                )
                raise SandboxError("Sandbox polling timed out") from exc
            except httpx.HTTPError as exc:  # pragma: no cover - network
                logger.error(
                    "sandbox_poll_failed",
                    extra={
                        "task_ref": task_ref,
                        "poll_url": poll_url,
                        "error": str(exc),
                    },
                )
                raise SandboxError("Sandbox polling failed") from exc

            self._raise_on_http_error(resp, task_ref)

            try:
                data = resp.json()
            except ValueError as exc:
                raise SandboxError("Invalid sandbox response") from exc

            last_payload = data
            if self._is_complete(data):
                return SandboxRunResult.from_payload(data)

        return SandboxRunResult(
            status="timeout",
            passed=0,
            failed=0,
            total=0,
            stdout="",
            stderr="Sandbox run timed out",
            raw=last_payload or None,
        )

    @staticmethod
    def _is_complete(data: dict[str, Any]) -> bool:
        if "result" in data:
            return True
        status_text = str(data.get("status") or "").lower()
        return status_text in {"passed", "failed", "timeout", "completed", "error"}

    @staticmethod
    def _raise_on_http_error(resp: httpx.Response, task_ref: str | None) -> None:
        if resp.status_code >= 400:
            logger.error(
                "sandbox_unavailable",
                extra={
                    "task_ref": task_ref,
                    "status_code": resp.status_code,
                    "path": resp.request.url.path if resp.request else None,
                },
            )
            raise SandboxError("Sandbox unavailable", status_code=resp.status_code)

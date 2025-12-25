import httpx
import pytest

from app.services.sandbox_client import SandboxClient, SandboxError


@pytest.mark.asyncio
async def test_sandbox_client_normalizes_success():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "result": {
                    "passed": 3,
                    "failed": 1,
                    "stdout": "ok",
                    "stderr": "",
                }
            },
        )
    )
    client = SandboxClient(
        base_url="http://sandbox.test", api_key="key", transport=transport
    )

    result = await client.run_tests(task_ref="task-1", code="print('hi')")

    assert result.status == "failed"
    assert result.passed == 3
    assert result.failed == 1
    assert result.total == 4
    assert result.stdout == "ok"
    assert result.stderr == ""


@pytest.mark.asyncio
async def test_sandbox_client_compile_error_marks_failed():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "result": {
                    "passed": 0,
                    "failed": 0,
                    "stdout": "",
                    "stderr": "SyntaxError: bad indentation",
                }
            },
        )
    )
    client = SandboxClient(base_url="http://sandbox.test", transport=transport)

    result = await client.run_tests(task_ref="task-1", code="broken")

    assert result.status == "failed"
    assert result.timeout is False
    assert result.stderr.startswith("SyntaxError")


@pytest.mark.asyncio
async def test_sandbox_client_timeout_response():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "result": {
                    "passed": 0,
                    "failed": 0,
                    "stdout": "",
                    "stderr": "Timed out",
                    "timeout": True,
                }
            },
        )
    )
    client = SandboxClient(base_url="http://sandbox.test", transport=transport)

    result = await client.run_tests(task_ref="task-1", code="long running")

    assert result.status == "timeout"
    assert result.timeout is True
    assert "Timed out" in result.stderr


@pytest.mark.asyncio
async def test_sandbox_client_network_timeout_raises():
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    transport = httpx.MockTransport(handler)
    client = SandboxClient(base_url="http://sandbox.test", transport=transport)

    with pytest.raises(SandboxError):
        await client.run_tests(task_ref="task-1", code="hang")


@pytest.mark.asyncio
async def test_sandbox_client_polls_until_complete():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/run":
            return httpx.Response(200, json={"runId": "abc", "status": "queued"})
        calls["count"] += 1
        if calls["count"] < 2:
            return httpx.Response(200, json={"status": "running"})
        return httpx.Response(
            200,
            json={"result": {"passed": 2, "failed": 0, "stdout": "ok", "stderr": ""}},
        )

    transport = httpx.MockTransport(handler)
    client = SandboxClient(
        base_url="http://sandbox.test",
        transport=transport,
        poll_interval_seconds=0.0,
        max_poll_seconds=1.0,
    )

    result = await client.run_tests(task_ref="task-1", code="print('hi')")

    assert calls["count"] >= 1
    assert result.status == "passed"
    assert result.passed == 2
    assert result.failed == 0
    assert result.total == 2
    assert result.stdout == "ok"


@pytest.mark.asyncio
async def test_sandbox_client_polls_and_times_out():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/run":
            return httpx.Response(200, json={"runId": "abc", "status": "queued"})
        return httpx.Response(200, json={"status": "running"})

    transport = httpx.MockTransport(handler)
    client = SandboxClient(
        base_url="http://sandbox.test",
        transport=transport,
        poll_interval_seconds=0.0,
        max_poll_seconds=0.05,
    )

    result = await client.run_tests(task_ref="task-1", code="print('hi')")

    assert result.status == "timeout"
    assert result.timeout is True
    assert result.passed == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_sandbox_client_4xx_raises_sandbox_error():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, json={"message": "unauthorized"})
    )
    client = SandboxClient(base_url="http://sandbox.test", transport=transport)

    with pytest.raises(SandboxError) as excinfo:
        await client.run_tests(task_ref="task-1", code="print('hi')")

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_sandbox_client_uses_auth_header_for_polling():
    seen_headers = {"auth": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/run":
            return httpx.Response(200, json={"runId": "abc", "status": "queued"})
        seen_headers["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"result": {"passed": 1, "failed": 0, "stdout": "", "stderr": ""}},
        )

    transport = httpx.MockTransport(handler)
    client = SandboxClient(
        base_url="http://sandbox.test",
        api_key="secret",
        transport=transport,
        poll_interval_seconds=0.0,
        max_poll_seconds=0.1,
    )

    await client.run_tests(task_ref="task-1", code="print('hi')")

    assert seen_headers["auth"] == "Bearer secret"


@pytest.mark.asyncio
async def test_sandbox_client_missing_run_id_raises():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"status": "queued"})
    )
    client = SandboxClient(base_url="http://sandbox.test", transport=transport)

    with pytest.raises(SandboxError):
        await client.run_tests(task_ref="task-1", code="print('hi')")


@pytest.mark.asyncio
async def test_sandbox_client_invalid_json_response():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"not-json")
    )
    client = SandboxClient(base_url="http://sandbox.test", transport=transport)

    with pytest.raises(SandboxError):
        await client.run_tests(task_ref="task-1", code="print('hi')")


@pytest.mark.asyncio
async def test_sandbox_client_status_text_passed_with_no_counts():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"status": "passed", "stdout": "ok"})
    )
    client = SandboxClient(base_url="http://sandbox.test", transport=transport)

    result = await client.run_tests(task_ref="task-1", code="print('hi')")

    assert result.status == "passed"
    assert result.total == 0

import os

import modal
from fastapi import FastAPI, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

app = modal.App("simuhire-sandbox-adapter")

image = modal.Image.debian_slim().pip_install("fastapi[standard]", "pydantic")

auth_scheme = HTTPBearer()


class RunRequest(BaseModel):
    """Request to run code against a task."""

    taskRef: str
    code: str = ""
    files: dict[str, str] = Field(default_factory=dict)
    timeout: float = 30.0


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("simuhire-sandbox-auth")],
)
@modal.asgi_app()
def fastapi_app():
    """FastAPI app for the sandbox adapter."""
    web = FastAPI()

    @web.get("/health")
    def health():
        return {"ok": True}

    @web.post("/run")
    async def run(req: RunRequest, request: Request):
        token = await auth_scheme(request)
        expected = os.environ.get("AUTH_TOKEN", "")
        if not expected or token.credentials != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # Temporary stub result so you can wire backend end-to-end now.
        return {
            "result": {
                "status": "passed",
                "passed": 1,
                "failed": 0,
                "stdout": f"stub run for {req.taskRef}",
                "stderr": "",
                "timeout": False,
            }
        }

    return web

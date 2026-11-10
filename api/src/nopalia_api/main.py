from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from nopalia_api.config import get_settings
from nopalia_api.db import get_engine
from nopalia_api.errors import ToolError
from nopalia_api.observability import configure_logging, request_context_middleware
from nopalia_api.routers import tools, webhooks
from nopalia_api.schemas import ErrorBody

configure_logging(get_settings().log_level)

app = FastAPI(
    title="Productos Nopalia — Back-office API (simulated)",
    version="0.2.0",
    description="Customer systems exposed as server tools for the 'Vera' voice agent.",
)
app.middleware("http")(request_context_middleware)
app.include_router(tools.router)
app.include_router(webhooks.router)


@app.exception_handler(ToolError)
async def tool_error_handler(_: Request, exc: ToolError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.body.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Same {code, message_es} shape as every other error, so the agent has one contract."""
    fields = [".".join(str(p) for p in e["loc"] if p != "body") for e in exc.errors()]
    body = ErrorBody(
        code="invalid_request",
        message_es="Faltan datos o tienen un formato incorrecto. Confirma con el cliente.",
        fields=fields,
    )
    return JSONResponse(status_code=422, content=body.model_dump())


@app.get("/health/live", tags=["ops"])
def live() -> dict[str, str]:
    """Liveness: the process is up. No dependencies, so a DB blip doesn't trigger restarts."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["ops"])
def ready() -> dict[str, str]:
    """Readiness: can serve traffic (DB reachable)."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}

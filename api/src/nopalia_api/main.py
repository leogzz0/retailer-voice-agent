from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from nopalia_api.db import get_engine
from nopalia_api.routers import tools
from nopalia_api.services import ToolError

app = FastAPI(
    title="Productos Nopalia — Back-office API (simulated)",
    version="0.1.0",
    description="Customer systems exposed as server tools for the 'Paty' voice agent.",
)
app.include_router(tools.router)


@app.exception_handler(ToolError)
async def tool_error_handler(_: Request, exc: ToolError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.body.model_dump())


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness + DB reachability. Cheap enough to poll."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Response
from fastapi.responses import FileResponse

from app.api.routes import router
from app.api.auth_routes import require_superadmin, router as auth_router
from app.api.usage_routes import router as usage_router
from app.core.config import get_settings
from app.database import SessionLocal, init_db
from app.services.auth import SessionPrincipal, bootstrap_superadmin


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        bootstrap_superadmin(db, get_settings())
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="埋点数据自助拉取工具", version="0.0.3", lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(usage_router)
    app.include_router(router)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(Path(__file__).parent / "web" / "index.html")

    @app.get("/assets/date-range-picker.js", include_in_schema=False)
    def date_range_picker_asset() -> FileResponse:
        return FileResponse(
            Path(__file__).parent / "web" / "date-range-picker.js",
            media_type="application/javascript",
        )

    @app.get("/admin/usage", include_in_schema=False)
    def usage_page(
        _: SessionPrincipal = Depends(require_superadmin),
    ) -> FileResponse:
        return FileResponse(Path(__file__).parent / "web" / "admin.html")

    return app


app = create_app()

"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.session import close_db, init_db
from app.services.monthly_reward_scheduler import (
    start_monthly_reward_scheduler,
    stop_monthly_reward_scheduler,
)
from app.services.subscription_reminder_scheduler import (
    start_subscription_scheduler,
    stop_subscription_scheduler,
)

setup_logging(debug=settings.DEBUG)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_runtime_requirements()

    logger.info(
        "app_startup",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        debug=settings.DEBUG,
        environment=settings.ENVIRONMENT,
    )
    logger.info(
        "wechat_http_config",
        wechat_ssl_verify=settings.WECHAT_SSL_VERIFY,
        wechat_http_trust_env=settings.WECHAT_HTTP_TRUST_ENV,
        wechat_ca_bundle_set=bool(settings.WECHAT_CA_BUNDLE),
    )
    await init_db()
    start_monthly_reward_scheduler()
    start_subscription_scheduler()

    yield

    await stop_monthly_reward_scheduler()
    await stop_subscription_scheduler()
    await close_db()
    logger.info("app_shutdown")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="分销商培训与智能问答系统后端接口",
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_v1_router, prefix="/api")

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
async def admin_page():
    admin_index = os.path.join(static_dir, "admin", "index.html")
    if not os.path.exists(admin_index):
        return {"detail": "Admin page not found"}
    return FileResponse(admin_index)


@app.get("/styles.css", include_in_schema=False)
async def admin_styles_alias():
    admin_styles = os.path.join(static_dir, "admin", "styles.css")
    if not os.path.exists(admin_styles):
        return {"detail": "Admin styles not found"}
    return FileResponse(admin_styles, media_type="text/css")


@app.get("/app.js", include_in_schema=False)
async def admin_script_alias():
    admin_script = os.path.join(static_dir, "admin", "app.js")
    if not os.path.exists(admin_script):
        return {"detail": "Admin script not found"}
    return FileResponse(admin_script, media_type="application/javascript")




@app.get("/health", tags=["系统"])
async def health_check():
    return {"status": "ok", "version": settings.VERSION}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )

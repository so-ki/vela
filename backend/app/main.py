from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, legal, onboarding, projects, scenarios, system
from app.core.config import get_settings
from app.core.database import init_db
from app.services.legal_ingest import ingest_corpus
from app.services.legal_monitor import scan_regulatory_updates

logger = logging.getLogger(__name__)


async def _corpus_agent_loop() -> None:
    from app.core.database import SessionLocal
    from app.services.corpus_maintenance_agent_service import run_corpus_maintenance_agent

    settings = get_settings()
    interval = max(1, int(settings.corpus_agent_interval_hours)) * 3600
    await asyncio.sleep(60)
    while True:
        try:
            db = SessionLocal()
            try:
                run_corpus_maintenance_agent(db, scheduled=True, sync_lexml=True, auto_reindex=True)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("corpus agent scheduled run failed: %s", exc)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    agent_task = None
    try:
        ingest_corpus(force=False)
        scan_regulatory_updates(force_reindex=False)
    except Exception:
        pass  # Chroma 未安装时跳过，/legal/index 可手动触发
    if get_settings().app_env.lower() != "test":
        agent_task = asyncio.create_task(_corpus_agent_loop())
    yield
    if agent_task is not None:
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=(
            "拉美涉外投资合规协查与法律风险简报助手。"
            "OpenAPI 文档：/docs · ReDoc：/redoc · "
            "集成说明见仓库 API.md"
        ),
        version="0.2.0-mvp",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(onboarding.router, prefix="/api/v1")
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(legal.router, prefix="/api/v1")
    app.include_router(scenarios.router, prefix="/api/v1")
    app.include_router(system.router, prefix="/api/v1")

    return app


app = create_app()

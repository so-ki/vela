from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError

from app.api import (
    auth,
    competition,
    delivery_assurance,
    legal,
    legal_source_versions,
    llm_settings,
    mechanism,
    onboarding,
    projects,
    scenarios,
    system,
)
from app.core.config import get_settings, validate_runtime_configuration
from app.core.database import init_db, validate_instance_database_boundary
from app.core.rate_limit import RateLimitMiddleware
from app.services.legal_ingest import ingest_corpus
from app.services.legal_monitor import scan_regulatory_updates
from app.services.checklist_payload_service import (
    CHECKLIST_REVISION_CONFLICT_MESSAGE,
    ChecklistRevisionConflict,
)

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
                # Scheduled web-process jobs are read-only.  Candidate corpus
                # changes must enter the human review queue and can never
                # rewrite the active, hash-pinned capability-pack artifact.
                run_corpus_maintenance_agent(db, scheduled=True, sync_lexml=False, auto_reindex=False)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("corpus agent scheduled run failed: %s", exc)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_runtime_configuration()
    init_db()
    validate_instance_database_boundary()
    from app.core.database import SessionLocal
    from app.services.version_readiness_service import build_version_readiness_report

    with SessionLocal() as readiness_db:
        version_readiness = build_version_readiness_report(
            readiness_db, environment=get_settings().app_env
        )
    if not version_readiness["ready"]:
        logger.warning(
            "persisted version readiness is %s; production readiness will fail closed: %s",
            version_readiness["status"],
            version_readiness["version_issues"],
        )
    agent_task = None
    try:
        ingest_corpus(force=False)
        scan_regulatory_updates(force_reindex=False)
    except Exception:
        pass  # Chroma 未安装时跳过，/legal/index 可手动触发
    if get_settings().app_env.lower() != "test" and get_settings().corpus_agent_enabled:
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
    validate_runtime_configuration(settings)
    app = FastAPI(
        title=settings.app_name,
        description=(
            "拉美涉外投资合规协查与法律风险简报助手。"
            + ("OpenAPI 文档：/docs · ReDoc：/redoc · " if not settings.is_production else "")
            + "集成说明见仓库 API.md"
        ),
        version="0.3.0-development-candidate",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    @app.exception_handler(ChecklistRevisionConflict)
    async def checklist_revision_conflict_handler(
        _request: Request,
        exc: ChecklistRevisionConflict,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(StaleDataError)
    async def stale_orm_write_handler(
        _request: Request,
        _exc: StaleDataError,
    ) -> JSONResponse:
        # Mapper versioning is the final guard for older service paths that
        # commit a checklist assignment directly.  Never expose SQL details.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": CHECKLIST_REVISION_CONFLICT_MESSAGE},
            headers={"Cache-Control": "no-store"},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware)

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(competition.router, prefix="/api/v1")
    app.include_router(delivery_assurance.router, prefix="/api/v1")
    app.include_router(onboarding.router, prefix="/api/v1")
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(legal.router, prefix="/api/v1")
    app.include_router(scenarios.router, prefix="/api/v1")
    app.include_router(system.router, prefix="/api/v1")
    app.include_router(llm_settings.router, prefix="/api/v1")
    app.include_router(mechanism.router, prefix="/api/v1")
    app.include_router(legal_source_versions.router, prefix="/api/v1")

    return app


app = create_app()

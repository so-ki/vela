from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, legal, scenarios, system
from app.core.config import get_settings
from app.core.database import init_db
from app.services.legal_ingest import ingest_corpus
from app.services.legal_monitor import scan_regulatory_updates


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    try:
        ingest_corpus(force=False)
        scan_regulatory_updates(force_reindex=False)
    except Exception:
        pass  # Chroma 未安装时跳过，/legal/index 可手动触发
    yield


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
    app.include_router(legal.router, prefix="/api/v1")
    app.include_router(scenarios.router, prefix="/api/v1")
    app.include_router(system.router, prefix="/api/v1")

    return app


app = create_app()

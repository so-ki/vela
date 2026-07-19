from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str


class SystemStatusResponse(BaseModel):
    database: str
    chroma: dict
    disclaimer_required: bool = True


class VersionReadinessResponse(BaseModel):
    schema_version: str
    status: str
    ready: bool
    enforced: bool
    environment: str
    checks: dict[str, str]
    object_counts: dict[str, int]
    registry_errors: list[str]
    version_issues: list[dict[str, str]]
    warnings: list[str]

    model_config = {"extra": "forbid"}

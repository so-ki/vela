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

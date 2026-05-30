from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class LegalHitResponse(BaseModel):
    id: str
    source: str
    source_label: str
    urn: str
    url: str
    title_pt: str
    title_zh: str
    excerpt_pt: str
    excerpt_zh: str
    validity: str
    level: str
    published_at: str
    match_score: float
    vector_similarity: float
    keyword_overlap: float
    requires_review: bool


class ChecklistItemWithLegalResponse(BaseModel):
    code: str
    title: str
    description: str
    priority: str
    relevance_score: int
    rationale: str
    matched_triggers: List[str]
    status: str
    legal_hits: List[LegalHitResponse]
    retrieval_status: str


class ChecklistSectionWithLegalResponse(BaseModel):
    dimension_id: str
    dimension_name: str
    dimension_name_pt: str
    description: str
    items: List[ChecklistItemWithLegalResponse]


class LegalRetrievalResponse(BaseModel):
    scenario_id: int
    total_hits: int
    zero_hit_items: List[str]
    sections: List[ChecklistSectionWithLegalResponse]
    disclaimer: str
    index_status: dict[str, Any]


class LegalIndexResponse(BaseModel):
    status: str
    message: str
    indexed: int
    collection: Optional[str] = None
    sources_breakdown: Optional[dict[str, int]] = None


class LegalStatusResponse(BaseModel):
    chroma_installed: bool
    document_count: int
    collection: str
    sources: dict[str, str] = Field(
        default_factory=lambda: {
            "lexml": "https://www.lexml.gov.br/",
            "stf": "https://portal.stf.jus.br/jurisprudencia/",
            "stj": "https://scon.stj.jus.br/SCON/",
        }
    )

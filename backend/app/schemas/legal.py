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
    sources_breakdown: Optional[dict[str, Any]] = None


class LegalStatusResponse(BaseModel):
    chroma_installed: bool
    document_count: int
    collection: str
    mode: str = "pending"
    corpus_version: str = "1.0"
    sources_breakdown: dict[str, int] = Field(default_factory=dict)
    sources: dict[str, str] = Field(
        default_factory=lambda: {
            "lexml": "https://www.lexml.gov.br/",
            "planalto": "http://www4.planalto.gov.br/legislacao/",
            "stf": "http://www.stf.jus.br/",
            "stj": "https://scon.stj.jus.br/SCON/",
            "trabalho": "https://www.gov.br/trabalho-e-emprego/pt-br",
            "previdencia": "https://www.gov.br/previdencia/pt-br",
            "jusbrasil": "https://www.jusbrasil.com.br/",
        }
    )


class LegalMonitorAlert(BaseModel):
    id: str
    level: str
    title: str
    message: str
    detected_at: str
    scenario_id: Optional[int] = None
    affected_checklist_codes: List[str] = Field(default_factory=list)


class LegalMonitorSubscription(BaseModel):
    scenario_id: int
    project_name: str = ""
    checklist_codes: List[str] = Field(default_factory=list)
    compliance_dimensions: List[str] = Field(default_factory=list)
    subscribed_at: str


class LegalMonitorDiff(BaseModel):
    computed_at: str
    changed_documents: List[dict[str, Any]] = Field(default_factory=list)
    affected_checklist_codes: List[str] = Field(default_factory=list)
    has_changes: bool = False


class LegalMonitorResponse(BaseModel):
    enabled: bool
    corpus_version: str
    document_count: int
    sources_breakdown: dict[str, int]
    index_mode: str
    last_scan_at: Optional[str] = None
    corpus_fingerprint: Optional[str] = None
    alerts: List[LegalMonitorAlert] = Field(default_factory=list)
    subscription_note: str = ""
    subscriptions: List[LegalMonitorSubscription] = Field(default_factory=list)
    subscription_count: int = 0
    last_diff: Optional[LegalMonitorDiff] = None


class LegalMonitorScanResponse(BaseModel):
    scanned_at: str
    corpus_fingerprint: str
    new_alerts: List[LegalMonitorAlert]
    alerts: List[LegalMonitorAlert]
    index: LegalIndexResponse
    diff: Optional[LegalMonitorDiff] = None


class LegalMonitorSubscribeRequest(BaseModel):
    scenario_id: int
    checklist_codes: Optional[List[str]] = None
    compliance_dimensions: Optional[List[str]] = None


class LegalCorpusDocument(BaseModel):
    id: str
    source: str
    urn: str
    url: str
    title_pt: str
    title_zh: str
    dimension: str
    level: str
    validity: str
    published_at: str
    tags: List[str] = Field(default_factory=list)
    checklist_codes: List[str] = Field(default_factory=list)
    text_pt: str
    text_zh: str


class LegalCorpusDocumentCreate(BaseModel):
    id: Optional[str] = None
    source: str = "lexml"
    urn: str
    url: str
    title_pt: str
    title_zh: str
    dimension: str
    level: str = "federal"
    validity: str = "vigente"
    published_at: str
    tags: List[str] = Field(default_factory=list)
    checklist_codes: List[str] = Field(default_factory=list)
    text_pt: str
    text_zh: str


class LegalCorpusDocumentUpdate(BaseModel):
    source: Optional[str] = None
    urn: Optional[str] = None
    url: Optional[str] = None
    title_pt: Optional[str] = None
    title_zh: Optional[str] = None
    dimension: Optional[str] = None
    level: Optional[str] = None
    validity: Optional[str] = None
    published_at: Optional[str] = None
    tags: Optional[List[str]] = None
    checklist_codes: Optional[List[str]] = None
    text_pt: Optional[str] = None
    text_zh: Optional[str] = None


class LegalCorpusListResponse(BaseModel):
    version: str
    total: int
    items: List[LegalCorpusDocument]


class LegalCorpusMutationResponse(BaseModel):
    item: LegalCorpusDocument
    version: str
    document_count: int


class LegalCorpusDeleteResponse(BaseModel):
    deleted_id: str
    version: str
    document_count: int


class LegalCorpusMetaDimension(BaseModel):
    id: str
    name: str


class LegalCorpusMetaChecklistCode(BaseModel):
    id: str
    title: str
    dimension: str


class LegalCorpusMetaResponse(BaseModel):
    version: str
    jurisdiction: str
    document_count: int
    sources: List[str]
    levels: List[str]
    dimensions: List[LegalCorpusMetaDimension]
    checklist_codes: List[LegalCorpusMetaChecklistCode]


class LegalCorpusReindexResponse(BaseModel):
    version: str
    index: LegalIndexResponse

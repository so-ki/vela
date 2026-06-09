from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_legal_user, get_current_user
from app.models.user import User
from app.schemas.legal import (
    LegalCorpusDeleteResponse,
    LegalCorpusDocument,
    LegalCorpusDocumentCreate,
    LegalCorpusDocumentUpdate,
    LegalCorpusListResponse,
    LegalCorpusMetaResponse,
    LegalCorpusMutationResponse,
    LegalCorpusReindexResponse,
    LegalIndexResponse,
    LegalMonitorDiff,
    LegalMonitorResponse,
    LegalMonitorScanResponse,
    LegalMonitorSubscribeRequest,
    LegalMonitorSubscription,
    LegalStatusResponse,
)
from app.services.audit import write_audit_log
from app.services.legal_corpus_service import (
    create_corpus_source,
    delete_corpus_source,
    get_corpus_meta,
    get_corpus_source,
    list_corpus_sources,
    rebuild_corpus_index,
    update_corpus_source,
)
from app.services.legal_ingest import get_index_status, ingest_corpus, load_corpus
from app.services.legal_monitor import (
    compute_corpus_diff,
    get_monitor_status,
    list_subscriptions,
    scan_regulatory_updates,
    upsert_scenario_subscription,
)
from app.services.playbook_deviation_service import deviation_stats, list_global_deviations
from app.services.reg_feed_service import get_reg_feed_status, scan_reg_feed

router = APIRouter(prefix="/legal", tags=["法源 RAG"])


@router.get("/status", response_model=LegalStatusResponse)
def legal_status(_: User = Depends(get_current_user)):
    idx = get_index_status()
    from app.core.chroma_client import COLLECTION_NAME, _chroma_available

    corpus = load_corpus()
    breakdown: dict[str, int] = {}
    for s in corpus.get("sources", []):
        src = s.get("source", "unknown")
        breakdown[src] = breakdown.get(src, 0) + 1

    return LegalStatusResponse(
        chroma_installed=_chroma_available,
        document_count=idx.get("document_count", 0),
        collection=COLLECTION_NAME,
        mode=idx.get("mode", "pending"),
        corpus_version=corpus.get("version", "1.0"),
        sources_breakdown=breakdown,
    )


@router.post("/index", response_model=LegalIndexResponse)
def build_index(
    force: bool = Query(default=False, description="强制重建索引"),
    _: User = Depends(get_current_user),
):
    result = ingest_corpus(force=force)
    return LegalIndexResponse(
        status=result["status"],
        message=result.get("message", ""),
        indexed=result.get("indexed", 0),
        collection=result.get("collection"),
        sources_breakdown=result.get("sources_breakdown"),
    )


@router.get("/monitor", response_model=LegalMonitorResponse)
def legal_monitor_status(_: User = Depends(get_current_user)):
    return LegalMonitorResponse(**get_monitor_status())


@router.post("/monitor/scan", response_model=LegalMonitorScanResponse)
def legal_monitor_scan(
    force_reindex: bool = Query(default=False, description="扫描同时强制重建索引"),
    _: User = Depends(get_current_user),
):
    result = scan_regulatory_updates(force_reindex=force_reindex)
    scan_reg_feed()
    return LegalMonitorScanResponse(
        scanned_at=result["scanned_at"],
        corpus_fingerprint=result["corpus_fingerprint"],
        new_alerts=result["new_alerts"],
        alerts=result["alerts"],
        index=LegalIndexResponse(
            status=result["index"]["status"],
            message=result["index"].get("message", ""),
            indexed=result["index"].get("indexed", 0),
            collection=result["index"].get("collection"),
            sources_breakdown=result["index"].get("sources_breakdown"),
        ),
        diff=LegalMonitorDiff(**result["diff"]) if result.get("diff") else None,
    )


@router.get("/monitor/diff", response_model=LegalMonitorDiff)
def legal_monitor_diff(_: User = Depends(get_current_legal_user)):
    state = get_monitor_status()
    if state.get("last_diff"):
        return LegalMonitorDiff(**state["last_diff"])
    return LegalMonitorDiff(**compute_corpus_diff())


@router.get("/monitor/subscriptions", response_model=list[LegalMonitorSubscription])
def legal_monitor_subscriptions(_: User = Depends(get_current_legal_user)):
    return [LegalMonitorSubscription(**item) for item in list_subscriptions()]


@router.post("/monitor/subscribe", response_model=LegalMonitorSubscription)
def legal_monitor_subscribe(
    body: LegalMonitorSubscribeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    from app.models.scenario import InvestigationScenario

    scenario = db.get(InvestigationScenario, body.scenario_id)
    if not scenario or not scenario.checklist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="场景不存在或未生成协查包")

    payload = scenario.checklist.payload or {}
    entry = upsert_scenario_subscription(
        body.scenario_id,
        scenario.project_name,
        payload,
        checklist_codes=body.checklist_codes,
        compliance_dimensions=body.compliance_dimensions or scenario.compliance_dimensions or [],
    )
    write_audit_log(
        db,
        user=user,
        action="monitor.subscribe",
        resource_type="scenario",
        resource_id=str(body.scenario_id),
        detail=f"codes={len(entry.get('checklist_codes') or [])}",
    )
    return LegalMonitorSubscription(**entry)


@router.get("/playbook/deviations")
def legal_playbook_deviations(
    pack_id: Optional[str] = Query(default=None),
    _: User = Depends(get_current_legal_user),
):
    from app.services.rules_pack_loop_service import generate_rules_pack_suggestions

    suggestions = generate_rules_pack_suggestions(pack_id)
    return {
        "stats": deviation_stats(),
        "deviations": list_global_deviations(limit=20),
        "rules_pack_loop": suggestions,
    }


@router.get("/playbook/rules-pack-suggestions")
def legal_rules_pack_suggestions(
    pack_id: Optional[str] = Query(default=None),
    min_reject_count: int = Query(default=2, ge=1, le=20),
    _: User = Depends(get_current_legal_user),
):
    from app.services.rules_pack_loop_service import (
        export_suggestion_draft_markdown,
        generate_rules_pack_suggestions,
    )

    result = generate_rules_pack_suggestions(pack_id, min_reject_count=min_reject_count)
    result["draft_markdown"] = export_suggestion_draft_markdown(result)
    return result


@router.get("/reg-feed")
def legal_reg_feed_status(_: User = Depends(get_current_legal_user)):
    return get_reg_feed_status()


@router.post("/reg-feed/scan")
def legal_reg_feed_scan(_: User = Depends(get_current_legal_user)):
    result = scan_reg_feed()
    scan_regulatory_updates(force_reindex=False)
    return result


@router.get("/corpus/meta", response_model=LegalCorpusMetaResponse)
def legal_corpus_meta(_: User = Depends(get_current_legal_user)):
    return LegalCorpusMetaResponse(**get_corpus_meta())


@router.get("/corpus", response_model=LegalCorpusListResponse)
def legal_corpus_list(
    q: Optional[str] = Query(default=None, description="搜索标题、id 或 checklist_code"),
    dimension: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    _: User = Depends(get_current_legal_user),
):
    result = list_corpus_sources(q=q, dimension=dimension, source=source)
    return LegalCorpusListResponse(**result)


@router.get("/corpus/{doc_id}", response_model=LegalCorpusDocument)
def legal_corpus_get(doc_id: str, _: User = Depends(get_current_legal_user)):
    return LegalCorpusDocument(**get_corpus_source(doc_id))


@router.post("/corpus", response_model=LegalCorpusMutationResponse)
def legal_corpus_create(
    payload: LegalCorpusDocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    result = create_corpus_source(payload.model_dump(exclude_none=True))
    write_audit_log(
        db,
        user=user,
        action="corpus.create",
        resource_type="legal_corpus",
        resource_id=result["item"]["id"],
        detail=f"version={result['version']}",
    )
    return LegalCorpusMutationResponse(
        item=LegalCorpusDocument(**result["item"]),
        version=result["version"],
        document_count=result["document_count"],
    )


@router.put("/corpus/{doc_id}", response_model=LegalCorpusMutationResponse)
def legal_corpus_update(
    doc_id: str,
    payload: LegalCorpusDocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    result = update_corpus_source(doc_id, payload.model_dump(exclude_none=True))
    write_audit_log(
        db,
        user=user,
        action="corpus.update",
        resource_type="legal_corpus",
        resource_id=doc_id,
        detail=f"version={result['version']}",
    )
    return LegalCorpusMutationResponse(
        item=LegalCorpusDocument(**result["item"]),
        version=result["version"],
        document_count=result["document_count"],
    )


@router.delete("/corpus/{doc_id}", response_model=LegalCorpusDeleteResponse)
def legal_corpus_delete(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    result = delete_corpus_source(doc_id)
    write_audit_log(
        db,
        user=user,
        action="corpus.delete",
        resource_type="legal_corpus",
        resource_id=doc_id,
        detail=f"version={result['version']}",
    )
    return LegalCorpusDeleteResponse(**result)


@router.post("/corpus/reindex", response_model=LegalCorpusReindexResponse)
def legal_corpus_reindex(
    force: bool = Query(default=True, description="强制重建索引"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    result = rebuild_corpus_index(force=force)
    write_audit_log(
        db,
        user=user,
        action="corpus.reindex",
        resource_type="legal_corpus",
        detail=result["index"].get("message"),
    )
    scan_regulatory_updates(force_reindex=False)
    return LegalCorpusReindexResponse(
        version=result["version"],
        index=LegalIndexResponse(
            status=result["index"]["status"],
            message=result["index"].get("message", ""),
            indexed=result["index"].get("indexed", 0),
            collection=result["index"].get("collection"),
            sources_breakdown=result["index"].get("sources_breakdown"),
        ),
    )


@router.post("/corpus/{doc_id}/lexml-sync")
def legal_corpus_lexml_sync(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    from app.services.lexml_fetch_service import enrich_corpus_document_from_lexml

    result = enrich_corpus_document_from_lexml(doc_id, persist=True)
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message"))
    if result.get("status") == "ok":
        rebuild_corpus_index(force=True)
    write_audit_log(
        db,
        user=user,
        action="corpus.lexml_sync",
        resource_type="legal_corpus",
        resource_id=doc_id,
        detail=result.get("message", ""),
    )
    return result


@router.get("/connector/search")
def brazil_connector_search(
    q: str = Query(..., min_length=2),
    dimension: str = Query(default="foreign_investment"),
    item_code: str = Query(default="GEN-001"),
    state: Optional[str] = Query(default=None),
    _: User = Depends(get_current_user),
):
    from app.services.brazil_connector_service import connector_retrieve_for_item

    hits, meta = connector_retrieve_for_item(
        item_code=item_code,
        dimension=dimension,
        title=q,
        description=q,
        state=state,
    )
    return {"query": q, "hits": hits, "meta": meta}


@router.get("/connector/status")
def brazil_connector_status(_: User = Depends(get_current_user)):
    from app.core.config import get_settings
    from app.services.brazil_connector_service import CITATION_TIERS
    from app.services.brazil_official_portals import list_portals, probe_official_endpoints

    settings = get_settings()
    probes = probe_official_endpoints()
    lexml_ok = any(p.get("reachable") for p in probes if p.get("id", "").startswith("lexml"))
    return {
        "connector": "brazil_legal",
        "citation_tiers": CITATION_TIERS,
        "official_source_chain": "语料库 → LexML URN 实时 → Planalto · STF · gov.br 门户",
        "modes": ["corpus_verified", "lexml_live", "portal_link"],
        "lexml_available_now": lexml_ok,
        "lexml_note": (
            "LexML 是巴西联邦官方法律文献统一检索与 URN 标识系统（lexml.gov.br），"
            "公开 HTTP 访问，无需 API Key；跨境网络可能较慢，本地语料优先。"
        ),
        "official_portals": list_portals(),
        "endpoint_probes": probes,
        "retrieval_top_k_default": settings.retrieval_top_k_default,
        "retrieval_top_k_max": 10,
    }


@router.get("/corpus-agent/status")
def corpus_agent_status(_: User = Depends(get_current_legal_user)):
    from app.services.corpus_maintenance_agent_service import get_agent_status

    return get_agent_status()


@router.post("/corpus-agent/run")
def corpus_agent_run(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
    sync_lexml: bool = Query(default=True),
    auto_reindex: bool = Query(default=True),
):
    from app.services.corpus_maintenance_agent_service import run_corpus_maintenance_agent

    result = run_corpus_maintenance_agent(
        db,
        scheduled=False,
        sync_lexml=sync_lexml,
        auto_reindex=auto_reindex,
    )
    write_audit_log(
        db,
        user=user,
        action="corpus_agent.run",
        resource_type="legal_corpus",
        resource_id=result.get("run_id"),
        detail=f"impacts={result.get('impacted_project_count', 0)}; sync={result.get('lexml_synced', 0)}",
    )
    return result


@router.post("/corpus-agent/notifications/{notification_id}/ack")
def corpus_agent_ack_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_legal_user),
):
    from app.services.corpus_maintenance_agent_service import acknowledge_notification

    result = acknowledge_notification(notification_id)
    if result.get("status") == "ok":
        write_audit_log(
            db,
            user=user,
            action="corpus_agent.ack",
            resource_type="notification",
            resource_id=notification_id,
        )
    return result

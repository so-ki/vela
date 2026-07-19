from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.roles import ROLE_BUSINESS
from app.models.mechanism import FactRecord, MaterialLedgerEntry
from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.competition import (
    CompetitionBusinessCenterResponse,
    CompetitionBusinessFact,
    CompetitionBusinessFactConfirmRequest,
    CompetitionBusinessMaterial,
    CompetitionBusinessProgress,
    CompetitionBusinessSupplement,
)
from app.schemas.mechanism import FactRecordCreateRequest, MaterialLedgerUpsertRequest
from app.services.audit import write_audit_log
from app.services.material_file_storage import (
    resolve_archived_file_path,
    save_scenario_material_files,
)
from app.services.mechanism_service import (
    confirm_fact_record,
    create_fact_record,
    upsert_material_ledger_entry,
)
from app.services.upload_security import read_upload_limited


router = APIRouter(prefix="/competition", tags=["比赛业务协同"])

_FACT_LABELS = {
    "origin": "投资主体",
    "destination_country": "目标国家",
    "destination_state": "目标地区",
    "industry": "项目行业",
    "action": "项目类型",
}
_MATERIAL_STATUS = {
    "missing": "待补充",
    "received": "已提交",
    "unreadable": "请重新上传",
    "ambiguous": "信息尚未确认",
    "verified": "已处理",
    "not_applicable": "无需提供",
}
_SUBMISSION_BLOCK_ID = "competition-business-supplement-submitted"


def _load_business_scenario(
    db: Session,
    scenario_id: int,
    user: User,
) -> InvestigationScenario:
    if get_settings().vela_app_mode != "competition":
        raise HTTPException(status_code=404, detail="比赛业务入口未启用")
    if user.role != ROLE_BUSINESS:
        raise HTTPException(status_code=403, detail="该入口仅供比赛业务账号使用")
    scenario = (
        db.query(InvestigationScenario)
        .filter(
            InvestigationScenario.id == scenario_id,
            InvestigationScenario.user_id == user.id,
            InvestigationScenario.is_demo.is_(False),
            InvestigationScenario.legal_deleted_at.is_(None),
        )
        .first()
    )
    if scenario is None:
        raise HTTPException(status_code=403, detail="无权访问该项目的业务中心")
    return scenario


def _has_business_submission(db: Session, scenario_id: int) -> bool:
    return (
        db.query(MaterialLedgerEntry.id)
        .filter(
            MaterialLedgerEntry.scenario_id == scenario_id,
            MaterialLedgerEntry.block_id == _SUBMISSION_BLOCK_ID,
        )
        .first()
        is not None
    )


def _business_center(
    db: Session,
    scenario: InvestigationScenario,
) -> CompetitionBusinessCenterResponse:
    ledger = (
        db.query(MaterialLedgerEntry)
        .filter(
            MaterialLedgerEntry.scenario_id == scenario.id,
            MaterialLedgerEntry.block_id != _SUBMISSION_BLOCK_ID,
        )
        .order_by(MaterialLedgerEntry.created_at.asc(), MaterialLedgerEntry.id.asc())
        .all()
    )
    materials = [
        CompetitionBusinessMaterial(
            id=entry.id,
            filename=entry.source_document,
            uploaded_at=entry.created_at,
            status=_MATERIAL_STATUS.get(entry.state, "处理中"),
        )
        for entry in ledger
    ]

    latest_by_attribute: dict[str, FactRecord] = {}
    fact_rows = (
        db.query(FactRecord)
        .filter(
            FactRecord.scenario_id == scenario.id,
            FactRecord.attribute.in_(tuple(_FACT_LABELS)),
        )
        .order_by(FactRecord.created_at.asc(), FactRecord.id.asc())
        .all()
    )
    for fact in fact_rows:
        latest_by_attribute[fact.attribute] = fact
    facts = [
        CompetitionBusinessFact(
            id=fact.id,
            label=_FACT_LABELS[attribute],
            value=fact.value,
            status="已确认" if fact.status == "business_confirmed" else "信息尚未确认",
        )
        for attribute, fact in latest_by_attribute.items()
    ]

    submitted = _has_business_submission(db, scenario.id)
    supplement_status = "已补充，法务复核中" if submitted else "待补充"
    supplements = [
        CompetitionBusinessSupplement(
            id="site-status",
            title="最终场址或选址状态",
            why="用于确认项目所在地及后续手续办理范围。",
            accepted_materials=["选址说明", "候选场址清单", "内部选址决策记录"],
            status=supplement_status,
        ),
        CompetitionBusinessSupplement(
            id="hazardous-inventory",
            title="危险品最大库存",
            why="用于判断仓储、消防及安全管理所需的项目条件。",
            accepted_materials=["物料清单", "安全数据表", "最大库存测算表"],
            status=supplement_status,
        ),
        CompetitionBusinessSupplement(
            id="equipment-activity",
            title="主要生产设备及活动分类",
            why="用于识别实际生产活动、设备规模和配套设施需求。",
            accepted_materials=["设备清单", "工艺流程图", "厂房功能布局说明"],
            status=supplement_status,
        ),
    ]

    if submitted:
        progress_states = ("completed", "completed", "completed", "current", "upcoming")
        current_status = "已补充，等待法务复核"
    else:
        progress_states = ("completed", "completed", "current", "upcoming", "upcoming")
        current_status = "待业务补充"
    progress = [
        CompetitionBusinessProgress(label=label, state=state)
        for label, state in zip(
            ("已提交", "法务处理中", "待业务补充", "已补充，等待法务复核", "已完成"),
            progress_states,
            strict=True,
        )
    ]
    return CompetitionBusinessCenterResponse(
        scenario_id=scenario.id,
        project_name=scenario.project_name,
        materials=materials,
        facts=facts,
        supplements=supplements,
        progress=progress,
        current_status=current_status,
    )


@router.get(
    "/scenarios/{scenario_id}/business-center",
    response_model=CompetitionBusinessCenterResponse,
)
def get_business_center(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_business_scenario(db, scenario_id, current_user)
    return _business_center(db, scenario)


@router.post(
    "/scenarios/{scenario_id}/business-center/materials",
    response_model=CompetitionBusinessCenterResponse,
)
async def post_business_material(
    scenario_id: int,
    purpose: Literal["project", "supplement"] = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_business_scenario(db, scenario_id, current_user)
    content = await read_upload_limited(file)
    filename = Path(file.filename or "business-material.bin").name
    archived: list[dict] = []
    try:
        archived = save_scenario_material_files(
            scenario.id,
            [(filename, content, file.content_type)],
        )
        block_id = f"competition-business-{purpose}:{uuid4().hex}"
        upsert_material_ledger_entry(
            db,
            scenario=scenario,
            block_id=block_id,
            request=MaterialLedgerUpsertRequest(
                source_document=filename,
                state="received",
                note="业务已上传补充材料" if purpose == "supplement" else "业务已上传项目材料",
            ),
            user=current_user,
            is_legal=False,
        )
        write_audit_log(
            db,
            user=current_user,
            action="competition.business_material_upload",
            resource_type="scenario",
            resource_id=str(scenario.id),
            detail=f"scenario={scenario.id} purpose={purpose} filename={filename}",
            commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        for item in archived:
            path = resolve_archived_file_path(scenario.id, str(item.get("stored_name") or ""))
            if path is not None:
                path.unlink(missing_ok=True)
        raise
    return _business_center(db, scenario)


@router.post(
    "/scenarios/{scenario_id}/business-center/facts/{fact_id}/confirm",
    response_model=CompetitionBusinessCenterResponse,
)
def post_business_fact_confirmation(
    scenario_id: int,
    fact_id: str,
    body: CompetitionBusinessFactConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_business_scenario(db, scenario_id, current_user)
    fact = db.get(FactRecord, fact_id)
    if (
        fact is None
        or fact.scenario_id != scenario.id
        or fact.attribute not in _FACT_LABELS
    ):
        raise HTTPException(status_code=404, detail="待确认信息不存在")
    value = body.value.strip()
    try:
        if value == fact.value and fact.status == "business_confirmed":
            return _business_center(db, scenario)
        if value != fact.value:
            fact = create_fact_record(
                db,
                scenario=scenario,
                request=FactRecordCreateRequest(
                    subject=fact.subject,
                    attribute=fact.attribute,
                    value=value,
                    fact_time=datetime.now(timezone.utc).date().isoformat(),
                    block_id=f"competition-business-fact:{uuid4().hex}",
                    fact_pack_version="aurora-business-confirmation-v1",
                    source_document="业务在线确认",
                    assertion_polarity=fact.assertion_polarity,
                ),
                user=current_user,
            )
        fact = confirm_fact_record(
            db,
            fact=fact,
            scenario=scenario,
            confirmation_note="业务账号确认该项为当前项目实际信息。",
            user=current_user,
        )
        write_audit_log(
            db,
            user=current_user,
            action="competition.business_fact_confirm",
            resource_type="fact",
            resource_id=fact.id,
            detail=f"scenario={scenario.id} field={fact.attribute}",
            commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _business_center(db, scenario)


@router.post(
    "/scenarios/{scenario_id}/business-center/submit",
    response_model=CompetitionBusinessCenterResponse,
)
def post_business_submission(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = _load_business_scenario(db, scenario_id, current_user)
    if not _has_business_submission(db, scenario.id):
        upsert_material_ledger_entry(
            db,
            scenario=scenario,
            block_id=_SUBMISSION_BLOCK_ID,
            request=MaterialLedgerUpsertRequest(
                source_document="业务补充信息",
                state="received",
                note="业务已提交法务复核",
            ),
            user=current_user,
            is_legal=False,
        )
        write_audit_log(
            db,
            user=current_user,
            action="competition.business_submit_to_legal",
            resource_type="scenario",
            resource_id=str(scenario.id),
            detail=f"scenario={scenario.id} status=awaiting_legal_review",
            commit=False,
        )
        db.commit()
    return _business_center(db, scenario)

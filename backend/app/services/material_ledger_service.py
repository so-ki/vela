"""六态材料账本服务：所有材料块状态迁移的唯一入口。

法域中立：本模块不得出现任何具体法域/语言内容。
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.statuses import MATERIAL_TRANSITIONS, MaterialBlockState
from app.models.material_ledger import MaterialBlock, MaterialBlockTransition


class InvalidTransitionError(Exception):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_block(
    db: Session,
    *,
    scenario_id: int,
    kind: str,
    filename: Optional[str] = None,
    stored_name: Optional[str] = None,
    content_bytes: Optional[bytes] = None,
    pack_id: Optional[str] = None,
    state: MaterialBlockState = MaterialBlockState.RAW_ARCHIVED,
) -> MaterialBlock:
    block = MaterialBlock(
        scenario_id=scenario_id,
        kind=kind,
        filename=filename,
        stored_name=stored_name,
        content_hash=_sha256(content_bytes) if content_bytes is not None else None,
        pack_id=pack_id,
        state=state.value,
    )
    db.add(block)
    db.flush()
    block.transitions.append(
        MaterialBlockTransition(
            from_state="",
            to_state=state.value,
            reason="block created",
        )
    )
    db.flush()
    return block


def transition(
    db: Session,
    block: MaterialBlock,
    to_state: MaterialBlockState,
    *,
    actor_user_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> MaterialBlock:
    """校验转移表后迁移状态；非法迁移抛 InvalidTransitionError。"""
    current = MaterialBlockState(block.state)
    if to_state not in MATERIAL_TRANSITIONS[current]:
        raise InvalidTransitionError(f"{current.value} -> {to_state.value} is not allowed")
    block.transitions.append(
        MaterialBlockTransition(
            from_state=current.value,
            to_state=to_state.value,
            actor_user_id=actor_user_id,
            reason=reason,
        )
    )
    block.state = to_state.value
    db.flush()
    return block


def bulk_transition(
    db: Session,
    scenario_id: int,
    to_state: MaterialBlockState,
    *,
    actor_user_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> int:
    """把场景下所有允许迁移的块推进到目标态；不允许的静默跳过（返回迁移数）。"""
    moved = 0
    blocks = db.query(MaterialBlock).filter(MaterialBlock.scenario_id == scenario_id).all()
    for block in blocks:
        current = MaterialBlockState(block.state)
        if to_state in MATERIAL_TRANSITIONS[current]:
            transition(db, block, to_state, actor_user_id=actor_user_id, reason=reason)
            moved += 1
    return moved


def record_intake(
    db: Session,
    *,
    scenario_id: int,
    pack_id: Optional[str],
    uploads: Optional[list[tuple[str, bytes, Optional[str]]]] = None,
    archived_files: Optional[list[dict[str, Any]]] = None,
    extract_snapshot: Optional[dict[str, Any]] = None,
    form_fingerprint: Optional[bytes] = None,
) -> dict[str, int]:
    """材料提交时建账：每个上传文件一个块；抽取快照一个块；
    纯表单提交时以 form_fingerprint 记一个 field_set 块（表单也是材料）。

    返回 {filename -> block_id}（快照块 key 为 "__extract__"，表单块为 "__form__"）。
    """
    block_by_name: dict[str, int] = {}
    stored_by_name = {
        str(f.get("filename")): str(f.get("stored_name") or "")
        for f in (archived_files or [])
        if isinstance(f, dict)
    }
    for item in uploads or []:
        filename, content, _content_type = item
        block = create_block(
            db,
            scenario_id=scenario_id,
            kind="file",
            filename=filename,
            stored_name=stored_by_name.get(filename) or None,
            content_bytes=content,
            pack_id=pack_id,
        )
        block_by_name[filename] = block.id

    if extract_snapshot:
        snap_block = create_block(
            db,
            scenario_id=scenario_id,
            kind="extract_snapshot",
            filename=str(extract_snapshot.get("filename") or "") or None,
            pack_id=pack_id,
        )
        facts = extract_snapshot.get("facts") or []
        all_verified = bool(facts) and all(
            (f.get("verification_status") == "verified") for f in facts if isinstance(f, dict)
        )
        transition(
            db,
            snap_block,
            MaterialBlockState.VERIFIED if all_verified else MaterialBlockState.UNVERIFIED,
            reason="extract snapshot attached",
        )
        block_by_name["__extract__"] = snap_block.id

    if not block_by_name and form_fingerprint is not None:
        form_block = create_block(
            db,
            scenario_id=scenario_id,
            kind="field_set",
            content_bytes=form_fingerprint,
            pack_id=pack_id,
        )
        transition(db, form_block, MaterialBlockState.EXTRACTED, reason="form fields submitted")
        block_by_name["__form__"] = form_block.id
    return block_by_name


def ledger_projection(db: Session, scenario_id: int) -> list[dict[str, Any]]:
    """账本只读投影，用于塞进 checklist payload 供前端/导出消费。"""
    blocks = (
        db.query(MaterialBlock)
        .filter(MaterialBlock.scenario_id == scenario_id)
        .order_by(MaterialBlock.id)
        .all()
    )
    return [
        {
            "block_id": b.id,
            "block_uid": b.block_uid,
            "kind": b.kind,
            "filename": b.filename,
            "state": b.state,
            "content_hash": b.content_hash,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        }
        for b in blocks
    ]

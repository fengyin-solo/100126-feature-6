"""温控监测接口：维护温度记录，覆盖转预警派单、挂起/恢复、处置完成、调度退回等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.temp import (
    DISPLAY_HANDLED,
    DISPLAY_IN_CONTROL,
    DISPLAY_SUSPENDED,
    DISPLAY_WARNING,
    TempService,
)

router = APIRouter(prefix="/api/temp", tags=["温控监测"])

service = TempService()

LIST_FIELDS = ["记录编号", "关联调度", "温区编号", "设定温度", "实际温度", "记录时间", "传感器编号", "温度状态"]
DISPLAY_STATUSES = [DISPLAY_IN_CONTROL, DISPLAY_WARNING, DISPLAY_SUSPENDED, DISPLAY_HANDLED]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="在控、预警、挂起中、已处置"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号与显示状态过滤温控监测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in DISPLAY_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"状态仅支持：{'、'.join(DISPLAY_STATUSES)}",
        )
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出温控监测清单：返回当前过滤条件下的全量数据。

    必须注册在 /{entry_id} 之前，否则 export 会被当成记录编号截获。
    """
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "temp", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条温度记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"温度记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条温度记录，缺字段时说明原因而不是静默丢弃。

    登记时若实际温度已偏离设定温度超过阈值，必须同时给出处置人员，
    记录直接以预警状态入库并派单。
    """
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}（超限记录必须当场指派处置人员）")
    return ActionResult(ok=True, message="温度记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条温度记录执行转预警派单、挂起、恢复、处置完成、调度退回。

    处置人员、处置措施、退回原因等随 values 一并提交；不允许的动作会被拦下并说明原因。
    """
    values = dict(payload.values or {})
    action = str(values.pop("action", "") or "").strip()
    if payload.remark and not values.get("备注"):
        values["备注"] = payload.remark
    entry, message = service.run_action(entry_id, action, values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

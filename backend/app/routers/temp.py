"""温控监测接口：温度记录登记、超限转预警、处置闭环、挂起恢复与调度退回。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.temp import TempService

router = APIRouter(prefix="/api/temp", tags=["温控监测"])

service = TempService()

LIST_FIELDS = ["记录编号", "关联调度", "温区编号", "设定温度", "实际温度", "温度阈值", "记录时间", "传感器编号", "处置人员"]
STATUSES = ["在控", "预警", "挂起", "已处置"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="在控、预警、挂起、已处置"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号与处置状态过滤温控监测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出温控监测清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "temp", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条温度记录明细（含处置轨迹）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"温度记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记温度记录；登记读数已超限时会自动转预警，此时必须指定处置人员。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if entry and entry.get("status") == "预警":
        message = "温度记录已登记，读数超限已自动转预警"
    else:
        message = "温度记录已登记"
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """处置动作：转预警、处置完成、挂起、恢复处置、调度退回；越权或越序都会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

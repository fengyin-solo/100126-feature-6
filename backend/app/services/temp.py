"""温控监测业务规则：超限处置状态流转、阈值判定与操作留痕都收在这里。

状态机（主状态 + 挂起标记，对外统一成一个显示状态）：

    在控 ──实际温度偏离设定温度超过阈值且指定处置人员──▶ 预警
    预警 ──挂起──▶ 预警（挂起中）──恢复──▶ 预警
    预警 ──处置完成（处置措施必填）──▶ 已处置
    已处置 ──调度退回（退回说明必填，仅调度可执行）──▶ 预警

同一条记录无论出现在列表页还是预警弹窗，都由 _decorate 统一计算显示状态，
避免两处各自维护口径。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "temp"
REQUIRED_FIELDS = ["记录编号", "关联调度", "温区编号"]

# 主状态：挂起不另立主状态，用 suspended 标记，恢复时不用倒主状态序列。
STATUS_IN_CONTROL = "在控"
STATUS_WARNING = "预警"
STATUS_HANDLED = "已处置"
STATUS_ORDER = [STATUS_IN_CONTROL, STATUS_WARNING, STATUS_HANDLED]

# 对外统一显示状态：列表页与预警弹窗都取这一个口径。
DISPLAY_IN_CONTROL = "在控"
DISPLAY_WARNING = "预警"
DISPLAY_SUSPENDED = "挂起中"
DISPLAY_HANDLED = "已处置"

# 实际温度偏离设定温度的默认阈值（℃），转预警时按 |实际-设定| 判定。
DEFAULT_THRESHOLD = 2.0

ACTION_DISPATCH = "转预警派单"
ACTION_SUSPEND = "挂起"
ACTION_RESUME = "恢复处置"
ACTION_COMPLETE = "处置完成"
ACTION_RETURN = "调度退回"
ACTION_RULES = {
    ACTION_DISPATCH: STATUS_WARNING,
    ACTION_SUSPEND: STATUS_WARNING,
    ACTION_RESUME: STATUS_WARNING,
    ACTION_COMPLETE: STATUS_HANDLED,
    ACTION_RETURN: STATUS_WARNING,
}
# 会让记录重新进入待处置口径的动作（挂起期间不算待办，退回后重新算）。
NEGATIVE_ACTIONS = [ACTION_RETURN]

DEFAULT_OPERATOR = "值班管理员"


def _now() -> str:
    """操作时间统一到秒，交班后接手的人看到的就是这个时间戳。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_temperature(value: Any) -> float | None:
    """把「-18」「-18.5℃」这类录入值解析成数字；解析不了返回 None，不猜值。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("℃", "").replace("°C", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _display_status(entry: dict[str, Any]) -> str:
    """唯一的显示状态口径：挂起标记叠在预警主状态上。"""
    if entry.get("status") == STATUS_HANDLED:
        return DISPLAY_HANDLED
    if entry.get("status") == STATUS_WARNING:
        return DISPLAY_SUSPENDED if entry.get("suspended") else DISPLAY_WARNING
    return DISPLAY_IN_CONTROL


def _decorate(entry: dict[str, Any]) -> dict[str, Any]:
    """列表与详情共用：补齐显示状态、偏离值与阈值，保证两处看到的状态一致。"""
    target = _parse_temperature(entry.get("设定温度"))
    actual = _parse_temperature(entry.get("实际温度"))
    entry["偏离值"] = round(abs(actual - target), 2) if target is not None and actual is not None else None
    entry["display_status"] = _display_status(entry)
    entry["温度状态"] = entry["display_status"]
    return entry


class TempService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            # 按统一显示状态过滤，"预警"只看未挂起的，"挂起中"单独筛。
            rows = [row for row in rows if _display_status(row) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [_decorate(dict(row)) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return _decorate(dict(entry))

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS:
            entry[field] = values.get(field)
        for field in ["设定温度", "实际温度", "记录时间", "传感器编号"]:
            entry[field] = values.get(field)
        if not entry.get("记录时间"):
            entry["记录时间"] = _now()

        threshold = _parse_temperature(values.get("偏差阈值"))
        entry["偏差阈值"] = threshold if threshold is not None else DEFAULT_THRESHOLD
        entry["status"] = STATUS_IN_CONTROL
        entry["suspended"] = False
        entry["处置人员"] = None
        entry["处置措施"] = None
        entry["预警时间"] = None
        entry["处置时间"] = None
        entry["退回原因"] = None
        entry["history"] = []
        entry["pending"] = False
        entry["abnormal"] = False

        # 登记即超限的：必须当场派给具体处置人员，否则不允许带着预警状态入库。
        target = _parse_temperature(entry.get("设定温度"))
        actual = _parse_temperature(entry.get("实际温度"))
        over_limit = (
            target is not None
            and actual is not None
            and abs(actual - target) > float(entry["偏差阈值"])
        )
        handler = str(values.get("处置人员") or "").strip()
        if over_limit:
            if not handler:
                return None, ["处置人员"]
            self._move_to_warning(entry, handler, str(values.get("备注") or "").strip())
        rows.append(entry)
        return _decorate(dict(entry)), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"温度记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于温控监测可执行范围"

        operator = str(values.get("操作人") or "").strip() or DEFAULT_OPERATOR
        remark = str(values.get("备注") or "").strip()
        current = entry.get("status")

        if action == ACTION_DISPATCH:
            return self._dispatch(entry, values, operator, remark, update_temperature=True)
        if action == ACTION_SUSPEND:
            if current != STATUS_WARNING or entry.get("suspended"):
                return None, "只有预警中的记录可以挂起；已挂起或已处置的记录无需再挂起"
            entry["suspended"] = True
            entry["pending"] = False
            self._log(entry, action, operator, remark or "处置中途挂起，等待恢复")
            return _decorate(dict(entry)), "处置已挂起，可随时在预警列表中恢复"
        if action == ACTION_RESUME:
            if current != STATUS_WARNING or not entry.get("suspended"):
                return None, "只有挂起中的记录可以恢复处置"
            entry["suspended"] = False
            entry["pending"] = True
            self._log(entry, action, operator, remark or "挂起结束，恢复处置")
            return _decorate(dict(entry)), "已恢复处置，预警继续派给原处置人员"
        if action == ACTION_COMPLETE:
            if current != STATUS_WARNING:
                return None, "只有预警中的记录可以标记已处置"
            if entry.get("suspended"):
                return None, "记录处于挂起中，请先恢复处置再标记已处置"
            measure = str(values.get("处置措施") or "").strip()
            if not measure:
                return None, "处置尚未完成：请填写处置措施后再标记已处置"
            entry["处置措施"] = measure
            entry["status"] = STATUS_HANDLED
            entry["suspended"] = False
            entry["pending"] = False
            entry["abnormal"] = False
            entry["处置时间"] = _now()
            self._log(entry, action, operator, remark or measure)
            return _decorate(dict(entry)), "处置已完成，记录标记为已处置"
        if action == ACTION_RETURN:
            if current != STATUS_HANDLED:
                return None, "只有已处置的记录可以由调度退回"
            role = str(values.get("操作角色") or "").strip()
            if role != "调度":
                return None, "已处置记录改结论必须由调度退回，请用调度身份操作"
            reason = str(values.get("退回原因") or values.get("备注") or "").strip()
            if not reason:
                return None, "调度退回必须填写退回原因"
            entry["status"] = STATUS_WARNING
            entry["suspended"] = False
            entry["pending"] = True
            entry["abnormal"] = True
            entry["处置措施"] = None
            entry["处置时间"] = None
            entry["退回原因"] = reason
            # 温区编号与记录时间保持原值，这里刻意不碰这两个字段。
            self._log(entry, action, operator, reason)
            return _decorate(dict(entry)), "调度已退回，记录回到预警，温区编号与记录时间不变"
        return None, f"动作「{action}」当前不可执行"

    # ---- 内部辅助 -------------------------------------------------------

    def _dispatch(
        self,
        entry: dict[str, Any],
        values: dict[str, Any],
        operator: str,
        remark: str,
        *,
        update_temperature: bool,
    ) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") != STATUS_IN_CONTROL:
            return None, "只有在控记录可以转预警；已预警的记录请直接处置或挂起"
        if update_temperature and values.get("实际温度") is not None:
            entry["实际温度"] = values.get("实际温度")
        target = _parse_temperature(entry.get("设定温度"))
        actual = _parse_temperature(entry.get("实际温度"))
        if target is None or actual is None:
            return None, "设定温度或实际温度无法识别，请先补全温度读数"
        threshold = _parse_temperature(values.get("偏差阈值"))
        if threshold is not None:
            entry["偏差阈值"] = threshold
        deviation = abs(actual - target)
        if deviation <= float(entry["偏差阈值"]):
            return None, (
                f"实际温度偏离设定温度 {deviation:.2f}℃，未超过阈值 "
                f"{entry['偏差阈值']}℃，不能转预警"
            )
        handler = str(values.get("处置人员") or "").strip()
        if not handler:
            return None, "转预警必须派给具体处置人员"
        self._move_to_warning(entry, handler, remark)
        return _decorate(dict(entry)), f"已转预警并派给{handler}"

    def _move_to_warning(self, entry: dict[str, Any], handler: str, remark: str) -> None:
        """登记/上报两条入口共用的转预警落库逻辑。"""
        entry["status"] = STATUS_WARNING
        entry["suspended"] = False
        entry["pending"] = True
        entry["abnormal"] = True
        entry["处置人员"] = handler
        entry["预警时间"] = _now()
        entry["退回原因"] = None
        self._log(entry, ACTION_DISPATCH, DEFAULT_OPERATOR, remark or f"派给{handler}")

    def _log(self, entry: dict[str, Any], action: str, operator: str, remark: str) -> None:
        entry.setdefault("history", []).append(
            {"动作": action, "操作人": operator, "备注": remark, "操作时间": _now()}
        )

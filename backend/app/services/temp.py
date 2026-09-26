"""温控监测业务规则：超限判定、处置状态流转与操作留痕都收在这里。

状态主线：在控 -> 预警 -> 已处置；「挂起」是预警的暂停态，只能恢复回预警继续处置，
不允许从挂起直接闭环。任何一步流转都写入「处置轨迹」，交班后接手人能看到上一步的
操作时间与备注；已处置记录只能由调度退回到预警，温区编号与记录时间始终不动。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from app.store import store

MODULE = "temp"
REQUIRED_FIELDS = ["记录编号", "关联调度", "温区编号"]
OPTIONAL_FIELDS = ["设定温度", "实际温度", "记录时间", "传感器编号"]
STATUSES = ["在控", "预警", "挂起", "已处置"]
DEFAULT_THRESHOLD = 2.0  # 实际温度偏离设定温度超过该值（℃）即判定超限

# 每个动作允许的前置状态：不在集合内的一律拒绝，保证流转只能沿状态线走。
ACTION_SOURCES: dict[str, set[str]] = {
    "转预警": {"在控"},
    "处置完成": {"预警"},
    "挂起": {"预警"},
    "恢复处置": {"挂起"},
    "调度退回": {"已处置"},
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_float(value: Any) -> float | None:
    """把「-18」「-18℃」这类读数解析成浮点数；解析不了返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("℃", "").replace("°C", "").replace("°c", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


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
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _text(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
        }
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            value = values.get(field)
            if _text(value) or (
                isinstance(value, (int, float)) and not isinstance(value, bool)
            ):
                entry[field] = value
        threshold = _to_float(values.get("温度阈值"))
        entry["温度阈值"] = threshold if threshold is not None else DEFAULT_THRESHOLD
        entry["status"] = "在控"
        entry["pending"] = True
        entry["abnormal"] = False
        entry["处置人员"] = _text(values.get("处置人员"))
        entry["处置轨迹"] = []
        self._trail(entry, "登记", values, "温度记录登记，进入在控")

        # 登记读数已经超限的，必须直接转预警并指定处置人员，不允许在在控状态下挂账。
        deviation = self._deviation(entry)
        if deviation is not None and deviation > entry["温度阈值"]:
            if not entry["处置人员"]:
                return None, ["处置人员（登记温度已超限，必须指定处置人员跟进）"]
            self._enter_alert(
                entry,
                values,
                f"登记读数偏离 {deviation:.1f}℃，超过阈值 {entry['温度阈值']}℃，自动转预警",
            )
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"温度记录 {entry_id} 不存在或已归档"
        if action not in ACTION_SOURCES:
            return None, f"动作「{action}」不属于温控处置的可执行范围"
        current = str(entry.get("status") or "")
        if current not in ACTION_SOURCES[action]:
            allowed = "、".join(sorted(ACTION_SOURCES[action]))
            return None, f"记录当前处于「{current}」，「{action}」只能在「{allowed}」状态下执行"
        handlers: dict[
            str,
            Callable[[dict[str, Any], dict[str, Any]], tuple[dict[str, Any] | None, str]],
        ] = {
            "转预警": self._to_alert,
            "处置完成": self._finish,
            "挂起": self._suspend,
            "恢复处置": self._resume,
            "调度退回": self._return_by_dispatch,
        }
        return handlers[action](entry, values)

    # ---- 各动作的具体规则 -------------------------------------------------

    def _to_alert(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        # 允许带上最新读数触发，避免拿登记时的旧读数误判。
        fresh = _to_float(values.get("实际温度"))
        if fresh is not None:
            entry["实际温度"] = fresh
        deviation = self._deviation(entry)
        if deviation is None:
            return None, "设定温度或实际温度缺失，无法判定是否超限，请先补录读数"
        threshold = _to_float(entry.get("温度阈值"))
        if threshold is None:
            threshold = DEFAULT_THRESHOLD
        if deviation <= threshold:
            return None, f"当前偏离 {deviation:.1f}℃，未超过阈值 {threshold}℃，不满足转预警条件"
        assignee = _text(values.get("处置人员")) or _text(entry.get("处置人员"))
        if not assignee:
            return None, "转预警必须指定处置人员，避免超限记录无人跟进"
        entry["处置人员"] = assignee
        self._enter_alert(
            entry, values, f"偏离 {deviation:.1f}℃ 超过阈值 {threshold}℃，派单给{assignee}"
        )
        return entry, f"已转预警并派单给{assignee}"

    def _finish(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        measure = _text(values.get("处置措施"))
        if not measure:
            return None, "处置措施为空说明处置尚未完成，不能标记已处置"
        entry["处置措施"] = measure
        entry["status"] = "已处置"
        entry["处置时间"] = _now()
        entry["pending"] = False
        entry["abnormal"] = False
        self._trail(entry, "处置完成", values, measure)
        return entry, "处置完成，记录已闭环"

    def _suspend(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        reason = _text(values.get("挂起原因")) or _text(values.get("备注"))
        if not reason:
            return None, "挂起必须填写挂起原因，恢复处置时才查得到上下文"
        entry["挂起原因"] = reason
        entry["status"] = "挂起"
        entry["挂起时间"] = _now()
        entry["pending"] = True
        entry["abnormal"] = True
        self._trail(entry, "挂起", values, reason)
        return entry, "已挂起；恢复入口保留，可随时回到预警继续处置"

    def _resume(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        entry["status"] = "预警"
        entry["恢复时间"] = _now()
        entry["pending"] = True
        entry["abnormal"] = True
        note = _text(values.get("备注")) or "挂起恢复，继续处置"
        self._trail(entry, "恢复处置", values, note)
        return entry, "已恢复为预警，可继续处置"

    def _return_by_dispatch(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if _text(values.get("岗位")) != "调度":
            return None, "已处置记录只能由调度岗位退回，当前岗位无权操作"
        reason = _text(values.get("退回原因")) or _text(values.get("备注"))
        if not reason:
            return None, "退回必须填写退回原因，便于重新处置时核对"
        # 只推翻处置结论：温区编号、记录时间等原始字段保持不动。
        entry.pop("处置措施", None)
        entry.pop("处置时间", None)
        entry["status"] = "预警"
        entry["退回时间"] = _now()
        entry["pending"] = True
        entry["abnormal"] = True
        self._trail(entry, "调度退回", values, reason)
        return entry, "已由调度退回到预警，需重新处置"

    # ---- 内部辅助 ---------------------------------------------------------

    def _deviation(self, entry: dict[str, Any]) -> float | None:
        target = _to_float(entry.get("设定温度"))
        actual = _to_float(entry.get("实际温度"))
        if target is None or actual is None:
            return None
        return abs(actual - target)

    def _enter_alert(
        self, entry: dict[str, Any], values: dict[str, Any], note: str
    ) -> None:
        deviation = self._deviation(entry)
        if deviation is not None:
            entry["偏离值"] = round(deviation, 1)
        entry["status"] = "预警"
        entry["预警时间"] = _now()
        entry["pending"] = True
        entry["abnormal"] = True
        self._trail(entry, "转预警", values, note)

    def _trail(
        self,
        entry: dict[str, Any],
        action: str,
        values: dict[str, Any],
        note: str,
    ) -> None:
        trail = entry.setdefault("处置轨迹", [])
        trail.append({
            "时间": _now(),
            "操作": action,
            "操作人": _text(values.get("操作人")) or "值班员",
            "岗位": _text(values.get("岗位")) or "—",
            "备注": note,
            "结果状态": entry.get("status"),
        })

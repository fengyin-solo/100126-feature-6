"""温控监测超限处置状态流转的回归测试。

直接覆盖业务规则（app.services.temp）：阈值派单、挂起/恢复、
处置完成前置条件、调度退回保号，以及列表与详情的状态口径一致。

运行：cd backend && PYTHONPATH=. python -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import unittest

from app.services import temp as temp_service_module
from app.services.temp import (
    ACTION_COMPLETE,
    ACTION_DISPATCH,
    ACTION_RESUME,
    ACTION_RETURN,
    ACTION_SUSPEND,
    DISPLAY_HANDLED,
    DISPLAY_IN_CONTROL,
    DISPLAY_SUSPENDED,
    DISPLAY_WARNING,
    MODULE,
    TempService,
)
from app.store import store


class TempWorkflowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # store 是进程级单例，测试期间备份并还原 temp 表，避免污染种子数据。
        self._backup = copy.deepcopy(store.rows(MODULE))
        store.rows(MODULE).clear()
        self.service = TempService()

    def tearDown(self) -> None:
        store.rows(MODULE).clear()
        store.rows(MODULE).extend(self._backup)

    def _create_in_control(self, actual: str = "-17.5") -> int:
        entry, missing = self.service.create_entry(
            {
                "记录编号": "TEMP-T1",
                "关联调度": "DISP-0001",
                "温区编号": "ZONE-1",
                "设定温度": "-18",
                "实际温度": actual,
                "记录时间": "2026-09-26 10:00:00",
            }
        )
        self.assertEqual(missing, [])
        self.assertEqual(entry["display_status"], DISPLAY_IN_CONTROL)
        return int(entry["id"])

    def _dispatch_warning(self, entry_id: int, actual: str = "-13.0") -> None:
        """在控记录上报超限温度并派单，进入预警。"""
        entry, message = self.service.run_action(
            entry_id,
            ACTION_DISPATCH,
            {"实际温度": actual, "处置人员": "张三", "操作人": "值班管理员", "备注": "白班派单"},
        )
        self.assertIsNotNone(entry, message)
        self.assertEqual(entry["display_status"], DISPLAY_WARNING)

    def test_create_over_limit_requires_handler(self) -> None:
        """登记即超限：没有处置人员不予入库；有处置人员直接预警派单。"""
        entry, missing = self.service.create_entry(
            {"记录编号": "TEMP-X", "关联调度": "D", "温区编号": "Z",
             "设定温度": "2", "实际温度": "9"}
        )
        self.assertIsNone(entry)
        self.assertEqual(missing, ["处置人员"])

        entry, missing = self.service.create_entry(
            {"记录编号": "TEMP-X", "关联调度": "D", "温区编号": "Z",
             "设定温度": "2", "实际温度": "9", "处置人员": "赵六"}
        )
        self.assertEqual(missing, [])
        self.assertEqual(entry["display_status"], DISPLAY_WARNING)
        self.assertEqual(entry["处置人员"], "赵六")
        self.assertTrue(entry["预警时间"])

    def test_dispatch_requires_threshold_breach_and_handler(self) -> None:
        """在控 → 预警：必须超阈值且派给具体人员。"""
        entry_id = self._create_in_control(actual="-19.0")

        entry, message = self.service.run_action(
            entry_id, ACTION_DISPATCH, {"实际温度": "-19.0", "处置人员": "张三"}
        )
        self.assertIsNone(entry)
        self.assertIn("未超过阈值", message)

        entry, message = self.service.run_action(
            entry_id, ACTION_DISPATCH, {"实际温度": "-13.0", "处置人员": "   "}
        )
        self.assertIsNone(entry)
        self.assertIn("处置人员", message)

        entry, message = self.service.run_action(
            entry_id,
            ACTION_DISPATCH,
            {"实际温度": "-13℃", "处置人员": "张三", "备注": "电话报修"},
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["display_status"], DISPLAY_WARNING)
        self.assertEqual(entry["处置人员"], "张三")
        self.assertTrue(entry["pending"])
        self.assertTrue(entry["abnormal"])
        self.assertEqual(entry["偏离值"], 5.0)
        self.assertEqual(entry["history"][-1]["动作"], ACTION_DISPATCH)

    def test_suspend_blocks_completion_and_resume_reopens(self) -> None:
        """挂起留有恢复入口；挂起期间不能标记已处置。"""
        entry_id = self._create_in_control()
        self._dispatch_warning(entry_id)

        entry, _ = self.service.run_action(entry_id, ACTION_SUSPEND, {"操作人": "张三", "备注": "等备件"})
        self.assertEqual(entry["display_status"], DISPLAY_SUSPENDED)
        self.assertFalse(entry["pending"])

        entry, message = self.service.run_action(
            entry_id, ACTION_COMPLETE, {"处置措施": "修好了"}
        )
        self.assertIsNone(entry)
        self.assertIn("先恢复处置", message)

        # 挂起状态下也不允许重复挂起
        entry, message = self.service.run_action(entry_id, ACTION_SUSPEND, {})
        self.assertIsNone(entry)

        entry, _ = self.service.run_action(
            entry_id, ACTION_RESUME, {"操作人": "李四(接班)", "备注": "备件到站"}
        )
        self.assertEqual(entry["display_status"], DISPLAY_WARNING)
        self.assertTrue(entry["pending"])
        self.assertEqual(entry["处置人员"], "张三")

    def test_completion_requires_measure(self) -> None:
        """处置没完成（无处置措施）不允许标记已处置。"""
        entry_id = self._create_in_control()
        self._dispatch_warning(entry_id)

        entry, message = self.service.run_action(entry_id, ACTION_COMPLETE, {})
        self.assertIsNone(entry)
        self.assertIn("处置措施", message)

        entry, message = self.service.run_action(
            entry_id, ACTION_COMPLETE, {"操作人": "李四", "处置措施": "更换风机继电器"}
        )
        self.assertEqual(entry["display_status"], DISPLAY_HANDLED)
        self.assertFalse(entry["pending"])
        self.assertTrue(entry["处置时间"])

        # 已处置后不能再次直接完成（改结论只能走调度退回）
        entry, message = self.service.run_action(
            entry_id, ACTION_COMPLETE, {"处置措施": "改口"}
        )
        self.assertIsNone(entry)

    def test_dispatch_return_keeps_identity_and_resets_handling(self) -> None:
        """已处置改结论只能调度退回：回到预警，温区编号与记录时间不变。"""
        entry_id = self._create_in_control()
        self._dispatch_warning(entry_id)
        self.service.run_action(
            entry_id, ACTION_COMPLETE, {"处置措施": "已补冷"}
        )

        # 非调度身份即使写了原因也不能退回
        entry, message = self.service.run_action(
            entry_id,
            ACTION_RETURN,
            {"操作人": "张三", "操作角色": "处置人员", "退回原因": "我想改"},
        )
        self.assertIsNone(entry)
        self.assertIn("调度", message)

        # 调度退回时原因必填
        entry, message = self.service.run_action(
            entry_id,
            ACTION_RETURN,
            {"操作人": "调度王五", "操作角色": "调度"},
        )
        self.assertIsNone(entry)
        self.assertIn("退回原因", message)

        entry, message = self.service.run_action(
            entry_id,
            ACTION_RETURN,
            {"操作人": "调度王五", "操作角色": "调度", "退回原因": "复测仍超标，重新处置"},
        )
        self.assertEqual(entry["display_status"], DISPLAY_WARNING)
        self.assertEqual(entry["温区编号"], "ZONE-1")
        self.assertEqual(entry["记录时间"], "2026-09-26 10:00:00")
        self.assertIsNone(entry["处置措施"])
        self.assertIsNone(entry["处置时间"])
        self.assertEqual(entry["退回原因"], "复测仍超标，重新处置")
        self.assertTrue(entry["pending"])
        self.assertEqual(entry["history"][-1]["动作"], ACTION_RETURN)

        # 退回后可再次正常处置完成
        entry, _ = self.service.run_action(
            entry_id, ACTION_COMPLETE, {"处置措施": "再次补冷并复测合格"}
        )
        self.assertEqual(entry["display_status"], DISPLAY_HANDLED)

    def test_list_and_detail_share_one_status_pipeline(self) -> None:
        """同一条记录在列表与详情里的显示状态必须一致。"""
        entry_id = self._create_in_control()
        self._dispatch_warning(entry_id)

        items, total = self.service.list_entries(keyword="TEMP-T1")
        detail = self.service.get_entry(entry_id)
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["display_status"], DISPLAY_WARNING)
        self.assertEqual(items[0]["温度状态"], DISPLAY_WARNING)
        self.assertEqual(items[0]["display_status"], detail["display_status"])

        self.service.run_action(entry_id, ACTION_SUSPEND, {"备注": "挂起"})
        items, _ = self.service.list_entries(keyword="TEMP-T1")
        detail = self.service.get_entry(entry_id)
        self.assertEqual(items[0]["display_status"], DISPLAY_SUSPENDED)
        self.assertEqual(items[0]["display_status"], detail["display_status"])

        suspended, _ = self.service.list_entries(status=DISPLAY_SUSPENDED)
        self.assertEqual(len(suspended), 1)
        warning, _ = self.service.list_entries(status=DISPLAY_WARNING)
        self.assertEqual(warning, [])

    def test_history_records_time_operator_and_remark_for_handover(self) -> None:
        """每步留痕：交班后接手人能看到上一步操作时间与备注。"""
        entry_id = self._create_in_control()
        self.service.run_action(
            entry_id, ACTION_DISPATCH, {"实际温度": "-13.0", "处置人员": "张三", "备注": "白班派单", "操作人": "值班管理员"}
        )
        self.service.run_action(
            entry_id, ACTION_SUSPEND, {"操作人": "张三", "备注": "等温控配件"}
        )
        self.service.run_action(
            entry_id, ACTION_RESUME, {"操作人": "夜班李四", "备注": "配件到站，接手恢复"}
        )
        self.service.run_action(
            entry_id, ACTION_COMPLETE, {"操作人": "夜班李四", "处置措施": "更换配件复测合格"}
        )

        detail = self.service.get_entry(entry_id)
        self.assertEqual([item["动作"] for item in detail["history"]],
                         [ACTION_DISPATCH, ACTION_SUSPEND, ACTION_RESUME, ACTION_COMPLETE])
        for item in detail["history"]:
            self.assertTrue(item["操作时间"])
            self.assertTrue(item["操作人"])
        self.assertEqual(detail["history"][1]["备注"], "等温控配件")
        self.assertEqual(detail["history"][2]["操作人"], "夜班李四")

    def test_illegal_actions_are_rejected(self) -> None:
        """非法动作与不存在的记录给出可读错误。"""
        entry_id = self._create_in_control()
        entry, message = self.service.run_action(entry_id, "不存在的动作", {})
        self.assertIsNone(entry)
        self.assertIn("不属于温控监测可执行范围", message)

        entry, message = self.service.run_action(99999, ACTION_DISPATCH, {})
        self.assertIsNone(entry)
        self.assertIn("不存在或已归档", message)

        # 在控状态不能挂起/完成/退回
        for action in (ACTION_SUSPEND, ACTION_RESUME, ACTION_COMPLETE, ACTION_RETURN):
            entry, _ = self.service.run_action(entry_id, action, {"处置措施": "x", "退回原因": "x"})
            self.assertIsNone(entry, f"在控状态不应允许 {action}")


if __name__ == "__main__":
    unittest.main()

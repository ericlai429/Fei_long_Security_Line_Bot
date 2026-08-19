import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.database import db
from app.services.email_helper import normalize_and_validate_email
from app.services.sheets_service import sheets_service
from app.services.pdf_service import pdf_service
from app.services.admin_service import admin_service
from app.services.line_service import line_service
from app.services.scheduler_service import scheduler_service
from app.services.rate_limit_service import rate_limiter

scheduler_service.set_line_service(line_service)
admin_service.set_scheduler_service(scheduler_service)

class TestTSGHSecuritySystem(unittest.TestCase):

    def test_00_email_normalization_and_fullwidth_fix(self):
        norm1, valid1, had1 = normalize_and_validate_email("EricLai429@gmail.com")
        self.assertEqual(norm1, "ericlai429@gmail.com")
        self.assertTrue(valid1)

        norm2, valid2, had2 = normalize_and_validate_email("EricLai429＠gmail。com")
        self.assertEqual(norm2, "ericlai429@gmail.com")
        self.assertTrue(valid2)
        self.assertTrue(had2)

    def test_01_sub_pin_verification(self):
        group_id = "test_leader_group_01"
        db.upsert_group(
            group_id,
            group_name="急診第一小隊",
            sheet_tab="急診與中控小隊",
            leader_email="EricLai429＠gmail。com",
            pin_code="8821"
        )

        group = db.get_group(group_id)
        self.assertEqual(group["leader_email"], "ericlai429@gmail.com")

        verified_err = db.verify_and_unlock(group_id, "0000")
        self.assertFalse(verified_err)

        verified_ok = db.verify_and_unlock(group_id, "8821")
        self.assertTrue(verified_ok)
        self.assertTrue(db.is_group_unlocked(group_id))

    def test_02_4hour_rate_limiting(self):
        """Test 4-hour anti-spam rate limiting in group."""
        group_id = "test_cooldown_group"
        user_id = "user_guard_999"

        rate_limiter.reset(group_id, user_id)

        # 1st call: Allowed
        allowed1, rem1 = rate_limiter.check_and_update(group_id, user_id, is_admin=False)
        self.assertTrue(allowed1)
        self.assertEqual(rem1, 0)

        # 2nd immediate call: Blocked with ~14400s (4 hours) remaining
        allowed2, rem2 = rate_limiter.check_and_update(group_id, user_id, is_admin=False)
        self.assertFalse(allowed2)
        self.assertTrue(rem2 > 14000)

        # Admin call: Always allowed
        allowed_admin, _ = rate_limiter.check_and_update(group_id, user_id, is_admin=True)
        self.assertTrue(allowed_admin)

    def test_03_sheets_parsing(self):
        sample_rows = [
            ["日期", "星期", "哨點/崗位", "早班 (07-19)", "晚班 (19-07)", "機動支援", "備註"],
            ["2026/08/01", "六", "急診哨", "賴冠堃", "黃大煊", "張大千", "正常勤務"]
        ]
        sheets_service.load_direct_table_data("三總保全內部群", sample_rows)
        parsed = sheets_service.get_parsed_schedule("三總保全內部群")
        self.assertIn("columns", parsed)
        self.assertIn("rows", parsed)
        self.assertTrue(len(parsed["rows"]) > 0)
        self.assertTrue(len(parsed["members"]) > 0)

    def test_04_pdf_generation(self):
        parsed = sheets_service.get_parsed_schedule("三總保全內部群")
        pdf_res = pdf_service.generate_schedule_pdf(parsed, "三總保全內部群")
        self.assertTrue(os.path.exists(pdf_res["file_path"]))
        self.assertTrue(os.path.getsize(pdf_res["file_path"]) > 1000)

    def test_05_admin_commands(self):
        db.add_authorized_role("test_user_chen", "admin")
        resp_id = admin_service.handle_admin_command("test_user_chen", "/我的ID")
        self.assertIn("test_user_chen", resp_id)

        resp_email = admin_service.handle_admin_command("test_user_chen", "/管理 設定信箱 tsgh_internal EricLai429＠gmail。com")
        self.assertIn("小隊長 Email 白名單已更新", resp_email)
        self.assertEqual(db.get_group("tsgh_internal")["leader_email"], "ericlai429@gmail.com")

    def test_06_group_name_mismatch_alert(self):
        db.upsert_group("mismatch_group_123", group_name="外部惡搞群", expected_group_name="三總保全內部群")
        scan_res = scheduler_service.check_all_group_names_and_alert()
        self.assertEqual(scan_res["status"], "completed")
        self.assertTrue(scan_res["alerts_sent_count"] >= 1)

    def test_07_smart_schedule_inspection(self):
        from app.services.inspector_service import schedule_inspector
        raw_data = [
            ["日期", "星期", "哨點/崗位", "早班 (07-19)", "晚班 (19-07)", "機動支援", "備註"],
            ["2026/08/01", "六", "急診哨", "陳冠冠", "賴小隊", "張大千", "正常勤務"],
            ["2026/08/01", "六", "大門哨", "王小明", "李大華", "-", "常規門禁"],
            ["2026/08/02", "日", "中控室", "趙大同", "周小倫", "-", "輪值"]
        ]
        report = schedule_inspector.inspect_schedule_data(raw_data, "測試分頁")
        self.assertEqual(report["status"], "success")
        self.assertTrue(report["health_score"] >= 80)
        self.assertTrue(report["header_alignment"]["date"]["is_aligned"])
        self.assertTrue(report["header_alignment"]["morning_shift"]["is_aligned"])
        self.assertTrue(report["header_alignment"]["evening_shift"]["is_aligned"])
        self.assertEqual(report["date_analysis"]["total_valid_dates"], 3)
        self.assertTrue(report["guard_analysis"]["unique_guards_count"] >= 7)

if __name__ == "__main__":
    unittest.main()

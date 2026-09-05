import os
import sys
import unittest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app

class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "healthy")

    def test_pwa_headers_and_content(self):
        res = self.client.get("/pwa")
        self.assertEqual(res.status_code, 200)
        self.assertIn("no-store", res.headers.get("Cache-Control", ""))
        self.assertIn("飛龍保全", res.text)
        self.assertIn("密碼", res.text)
        self.assertIn("金庫", res.text)

    def test_dual_pin_verification(self):
        # 1. Successful verification (Master qwer8875 + Sub 8888)
        res_ok = self.client.post("/api/auth/verify-pin", json={
            "group_id": "tsgh_internal",
            "master_pin": "qwer8875",
            "sub_pin": "8888"
        })
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json()["status"], "success")

        # 2. Failed verification (Wrong Master PIN)
        res_err_master = self.client.post("/api/auth/verify-pin", json={
            "group_id": "tsgh_internal",
            "master_pin": "wrongpass",
            "sub_pin": "8888"
        })
        self.assertEqual(res_err_master.status_code, 401)

        # 3. Failed verification (Wrong Sub PIN)
        res_err_sub = self.client.post("/api/auth/verify-pin", json={
            "group_id": "tsgh_internal",
            "master_pin": "qwer8875",
            "sub_pin": "0000"
        })
        self.assertEqual(res_err_sub.status_code, 401)

    def test_admin_page(self):
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)
        self.assertIn("飛龍保全", res.text)
        self.assertIn("試算表分頁名稱", res.text)

    def test_admin_groups_crud(self):
        tabs_res = self.client.get("/api/admin/tabs")
        self.assertEqual(tabs_res.status_code, 200)
        self.assertTrue(len(tabs_res.json()["tabs"]) > 0)

        create_res = self.client.post("/api/admin/groups", json={
            "group_id": "test_web_group_99",
            "group_name": "門診機動哨小隊",
            "expected_group_name": "門診機動哨小隊",
            "sheet_tab": "門診與機動小隊",
            "pin_code": "6688"
        })
        self.assertEqual(create_res.status_code, 200)
        self.assertEqual(create_res.json()["group"]["sheet_tab"], "門診與機動小隊")

        list_res = self.client.get("/api/admin/groups")
        self.assertEqual(list_res.status_code, 200)
        groups = list_res.json()["groups"]
        found = any(g["group_id"] == "test_web_group_99" for g in groups)
        self.assertTrue(found)

        del_res = self.client.delete("/api/admin/groups/test_web_group_99")
        self.assertEqual(del_res.status_code, 200)

    def test_live_schedule_zero_cache(self):
        res = self.client.get("/api/schedule/live?group_id=tsgh_internal&tab=三總保全內部群&master_pin=qwer8875&sub_pin=8888")
        self.assertEqual(res.status_code, 200)
        self.assertIn("no-store", res.headers.get("Cache-Control", ""))
        data = res.json()
        self.assertEqual(data["tab_name"], "三總保全內部群")
        self.assertTrue(len(data["rows"]) > 0)

    def test_schedule_version_handshake_and_alignment(self):
        for tab_name in ["4.三總工務所", "5.三總重症大樓"]:
            # 1. 握手端點
            r_hs = self.client.get(f"/api/schedule/handshake?tab={tab_name}&year=2026&month=9")
            self.assertEqual(r_hs.status_code, 200)
            self.assertIn("no-store", r_hs.headers.get("Cache-Control", ""))
            hs_data = r_hs.json()
            self.assertEqual(hs_data["status"], "connected")
            self.assertTrue(hs_data["has_file"])
            self.assertEqual(hs_data["row_count"], 30)
            self.assertTrue(len(hs_data["version_hash"]) > 0)

            # 2. 即時排班端點
            r_live = self.client.get(f"/api/schedule/live?tab={tab_name}&year=2026&month=9")
            self.assertEqual(r_live.status_code, 200)
            self.assertIn("no-store", r_live.headers.get("Cache-Control", ""))
            live_data = r_live.json()
            self.assertEqual(len(live_data["rows"]), 30)
            self.assertEqual(live_data["version_hash"], hs_data["version_hash"])

    def test_pdf_generate_and_download(self):
        res = self.client.get("/api/pdf/generate?group_id=tsgh_internal&tab=三總保全內部群")
        self.assertEqual(res.status_code, 200)
        file_id = res.json()["file_id"]
        
        dl_res = self.client.get(f"/api/pdf/download/{file_id}")
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.headers["content-type"], "application/pdf")
        self.assertIn("no-store", dl_res.headers.get("Cache-Control", ""))

    def test_admin_status(self):
        res = self.client.get("/api/admin/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("registered_groups", data)
        self.assertIn("available_tabs", data)
        self.assertEqual(data["master_pin"], "PBKDF2_PROTECTED")

    def test_google_drive_status_and_connect(self):
        # 1. Status query
        res_status = self.client.get("/api/admin/google-drive/status")
        self.assertEqual(res_status.status_code, 200)
        data = res_status.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("service_account_email", data)
        self.assertTrue(len(data["shared_files"]) > 0)

        # 2. Connect spreadsheet
        res_connect = self.client.post("/api/admin/google-drive/connect", json={
            "url_or_id": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
        })
        self.assertEqual(res_connect.status_code, 200)
        conn_data = res_connect.json()
        self.assertEqual(conn_data["spreadsheet_id"], "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")
        self.assertTrue(len(conn_data["available_tabs"]) > 0)

    def test_schedule_inspect_api(self):
        res = self.client.post("/api/admin/schedule/inspect", json={"tab_name": "三總保全內部群"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("health_score", data)
        self.assertIn("header_alignment", data)
        self.assertIn("date_analysis", data)
        self.assertIn("guard_analysis", data)

    def test_direct_schedule_upload_api(self):
        tsv_text = "日期\t星期\t哨點/崗位\t早班 (07-19)\t晚班 (19-07)\t機動支援\t備註\n2026/08/01\t六\t急診哨\t陳冠冠\t賴冠堃\t張大千\t正常勤務"
        res = self.client.post("/api/admin/schedule/upload-data", json={
            "tab_name": "三總保全內部群",
            "content": tsv_text
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["loaded_rows"], 2)
        self.assertEqual(data["inspection"]["health_score"], 100)
        self.assertEqual(data["inspection"]["rare_char_analysis"]["rare_chars_detected_count"], 1)

    def test_admin_update_schedule_slot(self):
        res = self.client.post("/api/admin/schedule/update-slot", json={
            "tab_name": "5.三總重症大樓",
            "date": "2026/09/05",
            "shift": "早班",
            "person": "葉榮東 (0926-348-665)"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("成功替換", data["message"])
        self.assertEqual(data["person"], "葉榮東 (0926-348-665)")

if __name__ == "__main__":
    unittest.main()


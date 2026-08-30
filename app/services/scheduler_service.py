import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.database import db
from app.config import settings

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.line_service = None

    def set_line_service(self, service):
        self.line_service = service

    def start(self):
        """Starts the daily 08:00 AM Group Name verification job and hourly dynamic cloud sync."""
        if not self.scheduler.running:
            # 1. Run every day at 08:00 AM
            self.scheduler.add_job(
                self.check_all_group_names_and_alert,
                trigger=CronTrigger(hour=8, minute=0),
                id="daily_group_name_check",
                name="每日上午8點群組名稱一致性偵測與通報",
                replace_existing=True
            )
            # 2. Run every hour dynamically at minute 0
            self.scheduler.add_job(
                self.sync_and_generate_hourly_schedule,
                trigger=CronTrigger(minute=0),
                id="hourly_cloud_sync_and_generate",
                name="每小時動態抓取雲端班表與自動生成",
                replace_existing=True
            )
            self.scheduler.start()
            logger.info("Scheduler started: Daily 08:00 AM Check & Hourly Cloud Sync are active.")

            # Trigger initial background sync on startup
            import threading
            threading.Thread(target=self.sync_and_generate_hourly_schedule, daemon=True).start()

    def sync_and_generate_hourly_schedule(self) -> dict:
        """
        每小時自動執行動態抓取雲端班表、比對異動、更新快照並預先生成最新班表快取。
        """
        logger.info("🔄 [Hourly Sync] Starting dynamic cloud schedule sync & generation...")
        now = datetime.now()
        current_year = now.year
        current_month = 9 if (now.year == 2026 and now.month in [8, 9]) else now.month

        # 1. 嘗試刷新 Google User OAuth 授權權杖並自動掃描雲端硬碟最新月份試算表
        try:
            from app.services.google_auth_service import get_or_refresh_google_user_credentials, auto_scan_drive_monthly_spreadsheets, TOKEN_PATH
            import json, os
            creds = get_or_refresh_google_user_credentials()
            if creds and creds.token:
                auto_scan_drive_monthly_spreadsheets(creds.token)
            elif os.path.exists(TOKEN_PATH):
                with open(TOKEN_PATH, "r", encoding="utf-8") as tf:
                    tdata = json.load(tf)
                    t_token = tdata.get("token", "")
                    if t_token:
                        auto_scan_drive_monthly_spreadsheets(t_token)
        except Exception as ex:
            logger.debug(f"[Hourly Sync] Token scan note: {ex}")

        # 2. 依序抓取各分頁最新班表資料並進行異動比對
        from app.services.sheets_service import sheets_service
        from app.services.change_detector_service import schedule_change_detector

        tabs = sheets_service.list_tabs()
        results = {
            "synced_at": now.isoformat(),
            "year": current_year,
            "month": current_month,
            "tabs_synced": [],
            "total_diffs_found": 0
        }

        for tab_name in tabs:
            try:
                old_rows = db.get_schedule_snapshot(tab_name)
                new_rows = sheets_service.get_raw_sheet_data(tab_name, year=current_year, month=current_month)

                if new_rows and len(new_rows) > 0:
                    diff_list = []
                    if old_rows and len(old_rows) > 0 and old_rows != new_rows:
                        diff_list = schedule_change_detector.analyze_diff(tab_name, old_rows, new_rows)
                        if diff_list:
                            logger.info(f"⚡ [Hourly Sync] Detected {len(diff_list)} changes in tab [{tab_name}], triggering debounce push.")
                            schedule_change_detector.record_and_schedule_push(tab_name, diff_list)
                            results["total_diffs_found"] += len(diff_list)

                    # 更新快照
                    db.save_schedule_snapshot(tab_name, new_rows)
                    # 預先生成解析後結構
                    parsed = sheets_service.get_parsed_schedule(tab_name, year=current_year, month=current_month)
                    results["tabs_synced"].append({
                        "tab": tab_name,
                        "rows_count": len(new_rows),
                        "members_count": len(parsed.get("members", [])),
                        "diffs": len(diff_list)
                    })
            except Exception as e:
                logger.error(f"[Hourly Sync] Error syncing tab [{tab_name}]: {e}")

        logger.info(f"✅ [Hourly Sync] Completed. Synced {len(results['tabs_synced'])} tabs, Total Diffs: {results['total_diffs_found']}")
        return results

    def check_all_group_names_and_alert(self) -> dict:
        """
        Scans all registered groups.
        If actual group name does not match expected name, posts alert to the group at 08:00.
        """
        logger.info("Running daily 08:00 AM Group Name Verification scan...")
        groups = db.list_groups()
        alerts_sent = []

        for g in groups:
            group_id = g.get("group_id")
            expected_name = g.get("expected_group_name") or g.get("group_name", "三總保全內部群")
            
            # Fetch actual name from LINE API if possible
            actual_name = g.get("group_name", "")
            if self.line_service:
                fetched_name = self.line_service.get_actual_group_name(group_id)
                if fetched_name:
                    actual_name = fetched_name
                    db.update_actual_group_name(group_id, actual_name)

            # Check for mismatch
            if actual_name and expected_name and actual_name.strip() != expected_name.strip():
                alert_text = (
                    "⚠️ 【群組名稱異常提醒】\n"
                    "未偵測到正確的工作群組名稱，請通知管理者重新設定正確「小群組名稱」。\n\n"
                    f"• 預期名稱：【{expected_name}】\n"
                    f"• 偵測名稱：【{actual_name}】\n"
                    "-----------------------------\n"
                    "💡 排班小姐可使用 <code>/管理 命名 [群組ID] [正確名稱]</code> 重新綁定。"
                )
                logger.warning(f"Group name mismatch for {group_id}! Expected: '{expected_name}', Actual: '{actual_name}'")
                
                if self.line_service:
                    self.line_service.push_text_message(group_id, alert_text)
                
                alerts_sent.append({
                    "group_id": group_id,
                    "expected": expected_name,
                    "actual": actual_name,
                    "alert_sent_at": datetime.now().isoformat()
                })

        return {
            "status": "completed",
            "scanned_groups": len(groups),
            "alerts_sent_count": len(alerts_sent),
            "alerts": alerts_sent
        }

scheduler_service = SchedulerService()

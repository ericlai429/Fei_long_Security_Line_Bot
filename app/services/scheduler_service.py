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
        """Starts the daily 08:00 AM Group Name verification job."""
        if not self.scheduler.running:
            # Run every day at 08:00 AM
            self.scheduler.add_job(
                self.check_all_group_names_and_alert,
                trigger=CronTrigger(hour=8, minute=0),
                id="daily_group_name_check",
                name="每日上午8點群組名稱一致性偵測與通報",
                replace_existing=True
            )
            self.scheduler.start()
            logger.info("Scheduler started: Daily 08:00 AM Group Name Check is active.")

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

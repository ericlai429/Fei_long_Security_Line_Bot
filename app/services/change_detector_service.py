import time
import logging
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.database import db
from app.services.line_service import line_service

logger = logging.getLogger("TSGH_ChangeDetector")

class ScheduleChangeDetector:
    """
    班表異動偵測、3分鐘延時推播與異動 Log 紀錄核心服務
    - 偵測 A 早班(日班)、B 晚班(夜班) 欄位之同仁新增、刪除、調班異動
    - 3 分鐘防抖動延時推播 (Debounce 180s)
    - 寫入審計異動 Log [分頁, 姓名, 新增/刪除, 班別(A/B), 原值, 新值, 時間]
    """
    def __init__(self, debounce_seconds: int = 180):
        self.debounce_seconds = debounce_seconds
        self._lock = threading.Lock()
        self.pending_debounce: Dict[str, Dict[str, Any]] = {}

    def analyze_diff(self, tab_name: str, old_rows: List[List[str]], new_rows: List[List[str]]) -> List[Dict[str, Any]]:
        if not old_rows or not new_rows or len(new_rows) < 2:
            return []

        header = [str(c).strip() for c in new_rows[0]]
        date_col = next((i for i, h in enumerate(header) if "日" in h and "期" in h), 0)
        post_col = next((i for i, h in enumerate(header) if "哨" in h or "崗" in h or "點" in h), 2)
        morn_col = next((i for i, h in enumerate(header) if any(k in h for k in ["早", "日", "白"])), 3)
        eve_col  = next((i for i, h in enumerate(header) if any(k in h for k in ["晚", "夜", "暗"])), 4)

        def build_row_map(rows_data):
            row_map = {}
            for r in rows_data[1:]:
                if not r or not any(str(c).strip() for c in r):
                    continue
                d = str(r[date_col]).strip() if date_col < len(r) else ""
                p = str(r[post_col]).strip() if post_col < len(r) else ""
                m = str(r[morn_col]).strip() if morn_col < len(r) else ""
                e = str(r[eve_col]).strip()  if eve_col < len(r) else ""
                if not d:
                    continue
                key = f"{d}@@{p}"
                
                import re
                m_set = set(filter(None, [x.strip() for x in re.split(r"[/,、\s]+", m) if x.strip() and x.strip() not in ["-", "休"]]))
                e_set = set(filter(None, [x.strip() for x in re.split(r"[/,、\s]+", e) if x.strip() and x.strip() not in ["-", "休"]]))
                row_map[key] = {"date": d, "post": p, "morning": m_set, "evening": e_set}
            return row_map

        old_map = build_row_map(old_rows)
        new_map = build_row_map(new_rows)
        all_keys = set(old_map.keys()).union(set(new_map.keys()))

        diff_list = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for key in sorted(all_keys):
            old_item = old_map.get(key, {"date": key.split("@@")[0], "post": key.split("@@")[1] if "@@" in key else "", "morning": set(), "evening": set()})
            new_item = new_map.get(key, {"date": key.split("@@")[0], "post": key.split("@@")[1] if "@@" in key else "", "morning": set(), "evening": set()})

            d = new_item["date"] or old_item["date"]
            p = new_item["post"] or old_item["post"]

            # 1. 早班 (A 日班) 差異
            added_morning = new_item["morning"] - old_item["morning"]
            removed_morning = old_item["morning"] - new_item["morning"]

            for name in added_morning:
                diff_list.append({
                    "timestamp": now_str,
                    "tab_name": tab_name,
                    "date": d,
                    "post": p,
                    "member_name": name,
                    "shift_type": "☀️ 早班 (07-19)",
                    "shift_code": "A",
                    "action": "新增 (排入)",
                    "old_val": "未排班",
                    "new_val": f"排入 {p} 早班",
                    "status": "已記錄"
                })

            for name in removed_morning:
                diff_list.append({
                    "timestamp": now_str,
                    "tab_name": tab_name,
                    "date": d,
                    "post": p,
                    "member_name": name,
                    "shift_type": "☀️ 早班 (07-19)",
                    "shift_code": "A",
                    "action": "刪除 (取消)",
                    "old_val": f"原為 {p} 早班",
                    "new_val": "取消排班",
                    "status": "已記錄"
                })

            # 2. 晚班 (B 夜班) 差異
            added_evening = new_item["evening"] - old_item["evening"]
            removed_evening = old_item["evening"] - new_item["evening"]

            for name in added_evening:
                diff_list.append({
                    "timestamp": now_str,
                    "tab_name": tab_name,
                    "date": d,
                    "post": p,
                    "member_name": name,
                    "shift_type": "🌆 晚班 (19-07)",
                    "shift_code": "B",
                    "action": "新增 (排入)",
                    "old_val": "未排班",
                    "new_val": f"排入 {p} 晚班",
                    "status": "已記錄"
                })

            for name in removed_evening:
                diff_list.append({
                    "timestamp": now_str,
                    "tab_name": tab_name,
                    "date": d,
                    "post": p,
                    "member_name": name,
                    "shift_type": "🌆 晚班 (19-07)",
                    "shift_code": "B",
                    "action": "刪除 (取消)",
                    "old_val": f"原為 {p} 晚班",
                    "new_val": "取消排班",
                    "status": "已記錄"
                })

        return diff_list

    def record_and_schedule_push(self, tab_name: str, diff_list: List[Dict[str, Any]]):
        if not diff_list:
            return

        db.add_schedule_change_logs(diff_list)
        logger.info(f"Recorded {len(diff_list)} schedule changes for tab [{tab_name}]")

        with self._lock:
            if tab_name in self.pending_debounce:
                old_timer = self.pending_debounce[tab_name].get("timer")
                if old_timer and old_timer.is_alive():
                    old_timer.cancel()
                self.pending_debounce[tab_name]["changes"].extend(diff_list)
                self.pending_debounce[tab_name]["last_modified"] = time.time()
            else:
                self.pending_debounce[tab_name] = {
                    "changes": list(diff_list),
                    "last_modified": time.time()
                }

            timer = threading.Timer(
                self.debounce_seconds,
                self._on_debounce_timeout,
                args=[tab_name]
            )
            timer.daemon = True
            self.pending_debounce[tab_name]["timer"] = timer
            timer.start()
            logger.info(f"Scheduled {self.debounce_seconds}s debounce push for tab [{tab_name}]")

    def _on_debounce_timeout(self, tab_name: str):
        with self._lock:
            pending = self.pending_debounce.pop(tab_name, None)

        if not pending or not pending.get("changes"):
            return

        changes = pending["changes"]
        logger.info(f"Triggering 3-min debounce broadcast for tab [{tab_name}] ({len(changes)} items)")
        message = self.format_broadcast_message(tab_name, changes)
        
        groups = db.get_groups_by_tab(tab_name)
        for g in groups:
            group_id = g.get("group_id")
            if group_id:
                line_service.send_group_broadcast(group_id, message)

    def format_broadcast_message(self, tab_name: str, changes: List[Dict[str, Any]]) -> str:
        now_str = datetime.now().strftime("%m/%d %H:%M")
        msg = f"📢 【三總保全 ｜ 班表異動即時推播】\n"
        msg += f"📋 分頁：{tab_name}\n"
        msg += f"⏱️ 異動時間：{now_str} (修改靜置 3 分鐘確認發送)\n"
        msg += f"────────────────\n"

        grouped = {}
        for c in changes:
            d = c["date"]
            if d not in grouped:
                grouped[d] = []
            grouped[d].append(c)

        for d, items in grouped.items():
            msg += f"📅 日期：{d}\n"
            for it in items:
                action_icon = "➕" if "新增" in it["action"] else "❌"
                msg += f"  {action_icon} [{it['shift_type']}] {it['post']} ➔ {it['member_name']} ({it['action']})\n"
            msg += "\n"

        msg += f"💡 最新班表詳情請參閱 PWA 行動系統：\n"
        msg += f"🔗 http://127.0.0.1:8088/pwa?tab={tab_name}"
        return msg.strip()

schedule_change_detector = ScheduleChangeDetector(debounce_seconds=180)

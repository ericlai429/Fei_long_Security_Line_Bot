import logging
from typing import Dict, Any, List, Optional
from app.database import db
from app.services.sheets_service import sheets_service
from app.config import settings

logger = logging.getLogger(__name__)

class AdminService:
    def __init__(self):
        self.scheduler_service = None

    def set_scheduler_service(self, scheduler):
        self.scheduler_service = scheduler

    def handle_admin_command(self, user_id: str, text: str) -> str:
        parts = text.strip().split()
        if not parts:
            return self.get_help_text()

        cmd = parts[0]
        args = parts[1:]

        if cmd in ["/我的ID", "/id", "/ID", "/myid"]:
            role_name = db.get_role_name(user_id)
            return (
                f"👤 您的 LINE 帳號識別碼 (User ID)：\n"
                f"<code>{user_id}</code>\n"
                f"當前系統權限角色：【{role_name}】\n\n"
                f"💡 需具備「Admin」、「排班小姐」或「經理」權限，方可管理隊長 Email 白名單。"
            )

        # Check Manager / Admin / Officer permission
        if not db.is_authorized_manager(user_id):
            return (
                "⚠️ 【權限不足】\n"
                "此管理指令僅限「Admin 系統管理員」、「排班小姐」與「保全經理」使用。\n"
                "其他人員無權新增、修改或刪除小隊長 Email 白名單。"
            )

        sub_cmd = args[0] if args else "幫助"

        if sub_cmd in ["幫助", "help", "說明"]:
            return self.get_help_text()

        elif sub_cmd in ["名冊", "權限", "roles"]:
            roles = db.list_authorized_roles()
            admins_str = "\n".join([f"  • {a}" for a in roles.get("admins", [])]) or "  • 暫無"
            officers_str = "\n".join([f"  • {o}" for o in roles.get("schedule_officers", [])]) or "  • 暫無 (最多2人)"
            managers_str = "\n".join([f"  • {m}" for m in roles.get("managers", [])]) or "  • 暫無"

            return (
                f"👑 【飛龍保全 核心管理人員名冊】\n"
                f"-----------------------------\n"
                f"【👑 Admin 系統管理員】：\n{admins_str}\n\n"
                f"【👩‍💼 排班小姐 (限2人)】：\n{officers_str}\n\n"
                f"【👔 保全經理】：\n{managers_str}\n"
                f"-----------------------------\n"
                f"🛡️ 以上 3 類角色具備新增/刪除小隊長 Email 白名單權限。"
            )

        elif sub_cmd in ["列表", "清單", "status"]:
            return self.list_group_status()

        # 只有 Admin、排班小姐、經理 可以設定小隊長信箱
        elif sub_cmd in ["設定信箱", "新增信箱", "信箱", "email", "mail"]:
            if len(args) < 3:
                return "⚠️ 格式錯誤！正確格式：\n<code>/管理 設定信箱 [群組ID或名稱] [小隊長Email]</code>\n範例：<code>/管理 設定信箱 tsgh_internal leader.chen@feilong.com</code>"
            group_key = args[1]
            email = args[2]
            group = self._resolve_group(group_key)
            if not group:
                group = db.upsert_group(group_key, group_name=group_key, leader_email=email)
            else:
                db.set_leader_email(group["group_id"], email)

            operator_role = db.get_role_name(user_id)
            return (
                f"✅ 【小隊長 Email 白名單已更新】\n"
                f"操作者：{operator_role}\n"
                f"群組：{group.get('group_name', group['group_id'])}\n"
                f"小隊長 Email：【{email.lower()}】\n"
                f"狀態：已登錄至飛龍白名單，初次呼叫時需以此信箱核對。"
            )

        # 只有 Admin、排班小姐、經理 可以刪除小隊長信箱
        elif sub_cmd in ["刪除信箱", "清除信箱", "remove_mail"]:
            if len(args) < 2:
                return "⚠️ 格式錯誤！正確格式：\n<code>/管理 刪除信箱 [群組ID或名稱]</code>"
            group_key = args[1]
            group = self._resolve_group(group_key)
            if not group:
                return f"⚠️ 找不到群組「{group_key}」。"

            db.delete_leader_email(group["group_id"])
            operator_role = db.get_role_name(user_id)
            return (
                f"🗑️ 【小隊長 Email 白名單已刪除】\n"
                f"操作者：{operator_role}\n"
                f"群組：{group.get('group_name', group['group_id'])}\n"
                f"該群組已解除隊長信箱綁定。"
            )

        elif sub_cmd in ["分頁列表", "tabs"]:
            tabs = sheets_service.list_tabs()
            tab_list = "\n".join([f"  • {t}" for t in tabs])
            return (
                f"📊 【Google 試算表現有分頁清單 (唯讀)】\n"
                f"-----------------------------\n"
                f"{tab_list}\n\n"
                f"💡 可使用 <code>/管理 綁定 [群組名稱/ID] [分頁名稱]</code> 進行指派。"
            )

        elif sub_cmd in ["綁定", "bind"]:
            if len(args) < 3:
                return "⚠️ 格式錯誤！正確格式：\n<code>/管理 綁定 [群組ID或名稱] [試算表分頁名稱]</code>\n範例：<code>/管理 綁定 tsgh_internal 第一小隊</code>"
            group_key = args[1]
            tab_name = args[2]
            
            group = self._resolve_group(group_key)
            if not group:
                group = db.upsert_group(group_key, group_name=group_key, sheet_tab=tab_name)
            else:
                db.set_group_tab(group["group_id"], tab_name)

            return (
                f"✅ 【分頁綁定成功】\n"
                f"群組：{group.get('group_name', group['group_id'])}\n"
                f"綁定分頁：【{tab_name}】\n"
                f"該群組的小隊長與成員往後查詢將自動讀取此分頁資料。"
            )

        elif sub_cmd in ["命名", "改名", "name"]:
            if len(args) < 3:
                return "⚠️ 格式錯誤！正確格式：\n<code>/管理 命名 [群組ID或名稱] [正確小群組名稱]</code>\n範例：<code>/管理 命名 tsgh_internal 三總保全內部群</code>"
            group_key = args[1]
            correct_name = args[2]
            group = self._resolve_group(group_key)
            if not group:
                group = db.upsert_group(group_key, group_name=correct_name, expected_group_name=correct_name)
            else:
                db.set_expected_group_name(group["group_id"], correct_name)
                db.update_actual_group_name(group["group_id"], correct_name)

            return (
                f"✅ 【群組名稱設定成功】\n"
                f"群組 ID：{group['group_id']}\n"
                f"設定預期名稱：【{correct_name}】\n"
                f"系統將於每日 08:00 比對群組名稱是否符合。"
            )

        elif sub_cmd in ["設定碼", "pin", "PIN", "密碼"]:
            if len(args) < 3:
                return "⚠️ 格式錯誤！正確格式：\n<code>/管理 設定碼 [群組ID或名稱] [3~4位數字]</code>\n範例：<code>/管理 設定碼 tsgh_internal 8821</code>"
            group_key = args[1]
            new_pin = args[2]

            if not (new_pin.isdigit() and 3 <= len(new_pin) <= 4):
                return "⚠️ 安全 輔 PIN 碼必須為 3 至 4 位純數字！"

            group = self._resolve_group(group_key)
            if not group:
                group = db.upsert_group(group_key, group_name=group_key, pin_code=new_pin)
            else:
                db.set_group_pin(group["group_id"], new_pin)

            return (
                f"🔒 【輔 PIN 碼更新成功】\n"
                f"群組：{group.get('group_name', group['group_id'])}\n"
                f"新輔密碼：【{new_pin}】\n\n"
                f"⚠️ 注意事項：舊解鎖狀態已失效，請告知小隊長。"
            )

        elif sub_cmd in ["新增幹部", "授權"]:
            if len(args) < 3:
                return "⚠️ 格式錯誤！正確格式：\n<code>/管理 新增幹部 [User_ID] [officer(排班小姐) / manager(經理) / admin]</code>"
            target_uid = args[1]
            role_type = args[2].lower()
            if role_type not in ["officer", "manager", "admin", "排班小姐", "經理"]:
                return "⚠️ 角色類別僅支援：officer (排班小姐) 或 manager (經理) 或 admin"
            
            normalized = "officer" if role_type in ["officer", "排班小姐"] else ("manager" if role_type in ["manager", "經理"] else "admin")
            db.add_manager_role(target_uid, normalized)
            return f"✅ 已成功將 <code>{target_uid}</code> 設為【{db.get_role_name(target_uid)}】"

        elif sub_cmd in ["檢查群組", "檢查名稱", "check"]:
            if self.scheduler_service:
                res = self.scheduler_service.check_all_group_names_and_alert()
                return (
                    f"🔍 【群組名稱一致性手動掃描完成】\n"
                    f"• 掃描群組數：{res['scanned_groups']}\n"
                    f"• 發送警報數：{res['alerts_sent_count']}"
                )
            return "⚠️ 排程服務尚未啟動。"

        else:
            return f"❓ 未知管理指令：{sub_cmd}\n請輸入 <code>/管理 幫助</code> 查看完整指令列表。"

    def _resolve_group(self, group_key: str) -> Optional[Dict[str, Any]]:
        group = db.get_group(group_key)
        if group:
            return group
        groups = db.list_groups()
        for g in groups:
            if g.get("group_name") == group_key or g.get("expected_group_name") == group_key or g.get("group_id") == group_key:
                return g
        if group_key.isdigit():
            idx = int(group_key) - 1
            if 0 <= idx < len(groups):
                return groups[idx]
        return None

    def list_group_status(self) -> str:
        groups = db.list_groups()
        if not groups:
            return "目前尚無任何群組設定紀錄。"

        lines = ["📋 【飛龍保全 各群組分頁與隊長 Email 清單】", "-----------------------------"]
        for idx, g in enumerate(groups, 1):
            unlocked_mark = "🔓 已解鎖" if g.get("is_unlocked") else "🔒 待驗證"
            email_mark = "✅ 已認證" if g.get("is_email_verified") else "⚠️ 待認證"
            email = g.get("leader_email") or "未設定(無白名單)"

            lines.append(
                f"[{idx}] {g.get('group_name')} ({g.get('group_id')})\n"
                f"  • 隊長Email: {email} ({email_mark})\n"
                f"  • 試算表分頁: 【{g.get('sheet_tab', '三總保全內部群')}】\n"
                f"  • 輔 PIN: {g.get('pin_code')} ({unlocked_mark})"
            )
        lines.append("-----------------------------")
        lines.append("💡 設定隊長信箱：<code>/管理 設定信箱 [編號] [Email]</code> (限Admin/小姐/經理)")
        lines.append("💡 刪除隊長信箱：<code>/管理 刪除信箱 [編號]</code> (限Admin/小姐/經理)")
        lines.append("💡 查看幹部名冊：<code>/管理 名冊</code>")
        return "\n".join(lines)

    def get_help_text(self) -> str:
        return (
            "👩‍💼 【飛龍保全 ｜ 幹部專屬操作手冊】\n"
            "（限 Admin、排班小姐、經理 執行）\n"
            "-----------------------------\n"
            "1️⃣ 查詢設定清單：\n"
            "  <code>/管理 列表</code>\n\n"
            "2️⃣ 新增/修改小隊長 Email 白名單：\n"
            "  <code>/管理 設定信箱 [群組編號] [Email]</code>\n\n"
            "3️⃣ 刪除小隊長 Email 白名單：\n"
            "  <code>/管理 刪除信箱 [群組編號]</code>\n\n"
            "4️⃣ 指定群組對應分頁：\n"
            "  <code>/管理 綁定 [群組編號] [分頁名稱]</code>\n\n"
            "5️⃣ 自訂小隊輔 PIN 碼 (3~4碼)：\n"
            "  <code>/管理 設定碼 [群組編號] [3~4位數字]</code>\n\n"
            "6️⃣ 查詢幹部授權名冊：\n"
            "  <code>/管理 名冊</code>\n"
            "-----------------------------\n"
            "🛡️ 嚴格權限控管：僅 Admin、排班小姐與經理有權維護白名單。"
        )

admin_service = AdminService()

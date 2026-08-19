import logging
from datetime import datetime
from typing import Dict, Any, Optional
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    UserSource,
    GroupSource,
    RoomSource
)
from app.config import settings
from app.database import db
from app.services.sheets_service import sheets_service
from app.services.pdf_service import pdf_service
from app.services.admin_service import admin_service
from app.services.rate_limit_service import rate_limiter

logger = logging.getLogger(__name__)

configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)

class LineService:
    def __init__(self):
        self.parser = WebhookParser(settings.LINE_CHANNEL_SECRET)

    def handle_webhook_payload(self, body_text: str, signature: str) -> bool:
        try:
            events = self.parser.parse(body_text, signature)
        except Exception as e:
            logger.error(f"Failed to verify LINE signature: {e}")
            return False

        for event in events:
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                self.process_text_message(event)

        return True

    def format_cooldown_time(self, remaining_seconds: int) -> str:
        hours = remaining_seconds // 3600
        minutes = (remaining_seconds % 3600) // 60
        if hours > 0:
            return f"{hours} 小時 {minutes} 分鐘"
        return f"{minutes} 分鐘"

    def process_text_message(self, event: MessageEvent):
        text = event.message.text.strip()
        reply_token = event.reply_token

        user_id = ""
        group_id = ""
        is_group = False

        if isinstance(event.source, UserSource):
            user_id = event.source.user_id
            group_id = user_id
            group_name = "個人測試視窗" if user_id in settings.admin_id_list or "test" in user_id else f"個人測試_{user_id[-4:]}"
        elif isinstance(event.source, GroupSource):
            user_id = getattr(event.source, 'user_id', None) or ""
            group_id = event.source.group_id
            group_name = "三總保全內部群"
            is_group = True
            actual = self.get_actual_group_name(group_id)
            if actual:
                group_name = actual
        elif isinstance(event.source, RoomSource):
            user_id = getattr(event.source, 'user_id', None) or ""
            group_id = event.source.room_id
            group_name = "保全工作小組"
            is_group = True
        else:
            group_id = "unknown_group"
            group_name = "未知群組"

        group = db.get_group(group_id)
        if not group:
            group = db.upsert_group(group_id, group_name=group_name, expected_group_name=group_name)

        is_admin_user = db.is_authorized_manager(user_id)

        # 0. Quick ID Query: /id, /我的id, /群組id
        if text.lower() in ["/我的id", "/id", "/myid", "/群組id", "/groupid", "查id", "群組id"]:
            if is_group:
                self.send_text_reply(
                    reply_token,
                    f"👥 【此 LINE 群組識別碼 (Group ID)】\n"
                    f"-----------------------------\n"
                    f"<code>{group_id}</code>\n"
                    f"-----------------------------\n"
                    f"💡 請將上方以「C」開頭的代碼複製，貼入後台的「群組代碼 / ID」欄位即可完成綁定！"
                )
            else:
                self.send_text_reply(
                    reply_token,
                    f"👤 【您的個人識別碼 (User ID)】\n"
                    f"-----------------------------\n"
                    f"<code>{user_id}</code>\n"
                    f"-----------------------------\n"
                    f"💡 若要查詢群組 ID，請將機器人邀請加入群組後，在群組內發送 <code>/我的ID</code>。"
                )
            return

        # 1. Admin Commands
        if text.startswith("/管理"):
            reply_text = admin_service.handle_admin_command(user_id, text)
            self.send_text_reply(reply_token, reply_text)
            return

        # 2. Leader / Member Shift Query & Unlock: /班表 [輔PIN碼] or /驗證 [輔PIN碼]
        if text.startswith("/驗證") or text.startswith("/班表") or text.startswith("/查班") or text.startswith("班表"):
            parts = text.split()
            
            # Extract PIN code (3~4 digits)
            input_pin = None
            if len(parts) > 1:
                for p in parts[1:]:
                    if p.isdigit():
                        input_pin = p
                        break

            # If user provided Sub PIN -> verify directly (Unlocking resets cooldown)
            if input_pin:
                if db.verify_and_unlock(group_id, input_pin):
                    rate_limiter.check_and_update(group_id, user_id, is_admin=True)
                    g = db.get_group(group_id)
                    tab_name = g.get("sheet_tab", "三總保全內部群")
                    flex_card = self.create_schedule_flex_card(group_id, g["group_name"], tab_name, unlock_success=True)
                    self.send_flex_reply(reply_token, "【飛龍保全】輔PIN碼驗證成功！班表已解鎖", flex_card)
                    return
                else:
                    self.send_text_reply(
                        reply_token,
                        f"❌ 【輔 PIN 碼錯誤】\n"
                        f"您輸入的 PIN 碼「{input_pin}」不正確，請向排班小姐確認。"
                    )
                    return

            # If no PIN provided, check if group is already unlocked
            if not db.is_group_unlocked(group_id):
                self.send_text_reply(
                    reply_token,
                    f"🔒 【此群組尚未通過安全解鎖】\n"
                    f"群組名稱：{group.get('group_name', '三總保全內部群')}\n"
                    f"綁定分頁：{group.get('sheet_tab', '三總保全內部群')}\n\n"
                    f"💡 小隊長或同仁請輸入：<code>/班表 [輔PIN碼]</code>\n"
                    f"範例：<code>/班表 8888</code>\n\n"
                    f"（一經解鎖永久有效，直到排班小姐更換安全碼）"
                )
                return

            # 🛡️ 4 小時冷卻防洗頻限制檢查 (群組測試階段防惡意洗頻)
            can_call, remaining = rate_limiter.check_and_update(group_id, user_id, is_admin=is_admin_user)
            if not can_call:
                tab_name = group.get("sheet_tab", "三總保全內部群")
                pwa_url = f"{settings.BASE_URL}/pwa?group_id={group_id}&tab={tab_name}"
                cooldown_str = self.format_cooldown_time(remaining)

                self.send_text_reply(
                    reply_token,
                    f"⏳ 【防洗頻冷卻中】\n"
                    f"-----------------------------\n"
                    f"測試階段限制：每位同仁每 4 小時僅可呼叫一次群組班表。\n\n"
                    f"⌛ 您距離下次可呼叫時間尚有：\n"
                    f"👉 【{cooldown_str}】\n\n"
                    f"💡 建議方式：您可直接點擊下方 PWA 連結進行即時查班 (不限次數且不留暫存)：\n"
                    f"🔗 {pwa_url}"
                )
                return

            # Allowed! Return the Schedule Flex Card
            tab_name = group.get("sheet_tab", "三總保全內部群")
            flex_card = self.create_schedule_flex_card(group_id, group["group_name"], tab_name)
            self.send_flex_reply(reply_token, f"【飛龍保全】{tab_name} 排班表", flex_card)
            return

        # 3. Individual Shift: /我的班表
        if text.startswith("/我的班表"):
            parts = text.split()
            target_name = parts[1] if len(parts) > 1 else ""
            if not db.is_group_unlocked(group_id):
                self.send_text_reply(reply_token, "🔒 請先輸入 <code>/班表 [輔PIN碼]</code> 解鎖群組權限後再查詢。")
                return

            tab_name = group.get("sheet_tab", "三總保全內部群")
            schedule_data = sheets_service.get_parsed_schedule(tab_name)
            
            member_rows = []
            for r in schedule_data.get("rows", []):
                for k, v in r.items():
                    if target_name in str(v):
                        member_rows.append(f"📅 {r.get('日期', '')} ({r.get('星期', '')}) ｜ {r.get('哨點/崗位', '')}：{k}")

            if not member_rows:
                self.send_text_reply(reply_token, f"ℹ️ 在分頁【{tab_name}】中查無同仁「{target_name}」的排班記錄。")
            else:
                resp = f"👮 【同仁出勤明細 - {target_name}】\n分頁：{tab_name}\n" + "-"*25 + "\n"
                resp += "\n".join(member_rows[:15])
                self.send_text_reply(reply_token, resp)
            return

        # 4. Fallback Help
        if text in ["/help", "/幫助", "幫助", "查班"]:
            self.send_text_reply(
                reply_token,
                "👮 【飛龍保全 三總排班機器人 指令手冊】\n"
                "-----------------------------\n"
                "1️⃣ 查詢群組 ID：\n"
                "  <code>/我的ID</code> (在群組中發送獲取群組ID)\n\n"
                "2️⃣ 解鎖/查詢群組班表：\n"
                "  <code>/班表 [輔PIN碼]</code> (例如：<code>/班表 8888</code>)\n"
                "  （測試階段每人每 4 小時限呼叫 1 次防洗頻）\n\n"
                "3️⃣ 查詢個人出勤：\n"
                "  <code>/我的班表 [姓名]</code>\n\n"
                "4️⃣ 排班小姐/經理 後台管理：\n"
                "  <code>/管理 列表</code>\n"
                "-----------------------------\n"
                "🛡️ 輔 PIN 碼一經解鎖永久有效；PWA 查班無次數限制。"
            )

    def get_actual_group_name(self, group_id: str) -> Optional[str]:
        if not group_id or not group_id.startswith("C"):
            return None
        if settings.LINE_CHANNEL_ACCESS_TOKEN == "mock_token":
            return None
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                summary = line_bot_api.get_group_summary(group_id)
                return summary.group_name
        except Exception as e:
            logger.debug(f"Could not fetch group summary for {group_id}: {e}")
            return None

    def push_text_message(self, to_id: str, text: str):
        if settings.LINE_CHANNEL_ACCESS_TOKEN == "mock_token":
            logger.info(f"[MOCK LINE PUSH MESSAGE] To={to_id} Text={text}")
            return
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=to_id,
                        messages=[TextMessage(text=text)]
                    )
                )
        except Exception as e:
            logger.error(f"Failed to push LINE message to {to_id}: {e}")

    def create_schedule_flex_card(self, group_id: str, group_name: str, tab_name: str, unlock_success: bool = False) -> Dict[str, Any]:
        schedule_data = sheets_service.get_parsed_schedule(tab_name)
        pdf_meta = pdf_service.generate_schedule_pdf(schedule_data, group_name)
        
        pdf_download_url = f"{settings.BASE_URL}/api/pdf/download/{pdf_meta['file_id']}"
        pwa_url = f"{settings.BASE_URL}/pwa?group_id={group_id}&tab={tab_name}"

        status_text = "🎉 輔 PIN 碼驗證成功！群組已永久解鎖。" if unlock_success else "⚡ 已連線 Google 試算表 (最新排班)"

        bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0284c7",
                "paddingAll": "15px",
                "contents": [
                    {
                        "type": "text",
                        "text": "飛龍保全 ｜ 三總勤務排班",
                        "weight": "bold",
                        "color": "#ffffff",
                        "size": "sm"
                    },
                    {
                        "type": "text",
                        "text": f"📋 {tab_name}",
                        "weight": "bold",
                        "color": "#ffffff",
                        "size": "xl",
                        "margin": "sm"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": status_text,
                        "size": "xs",
                        "color": "#059669" if unlock_success else "#0284c7",
                        "weight": "bold"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "xs",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {"type": "text", "text": "授權群組", "color": "#64748b", "size": "sm", "flex": 2},
                                    {"type": "text", "text": group_name, "color": "#1e293b", "size": "sm", "flex": 4, "weight": "bold"}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {"type": "text", "text": "同步時間", "color": "#64748b", "size": "sm", "flex": 2},
                                    {"type": "text", "text": datetime.now().strftime("%H:%M:%S (即時)"), "color": "#1e293b", "size": "sm", "flex": 4}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {"type": "text", "text": "防護限制", "color": "#64748b", "size": "sm", "flex": 2},
                                    {"type": "text", "text": "⏱️ 每4小時限1次 (防洗頻)", "color": "#0d9488", "size": "sm", "flex": 4}
                                ]
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#0284c7",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "📄 下載 PDF 規格班表",
                            "uri": pdf_download_url
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "📱 開啟 PWA 即時查班 (雙PIN)",
                            "uri": pwa_url
                        }
                    }
                ]
            }
        }
        return bubble

    def send_text_reply(self, reply_token: str, text: str):
        if settings.LINE_CHANNEL_ACCESS_TOKEN == "mock_token":
            logger.info(f"[MOCK LINE REPLY] Token={reply_token} Text={text}")
            return
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=text)]
                )
            )

    def send_flex_reply(self, reply_token: str, alt_text: str, flex_dict: Dict[str, Any]):
        if settings.LINE_CHANNEL_ACCESS_TOKEN == "mock_token":
            logger.info(f"[MOCK LINE FLEX REPLY] AltText={alt_text}")
            return
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[FlexMessage(alt_text=alt_text, contents=FlexContainer.from_dict(flex_dict))]
                )
            )

line_service = LineService()

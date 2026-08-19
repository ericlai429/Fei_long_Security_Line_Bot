import os
import uuid
import logging
import re
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request, Header, HTTPException, Response, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import db
from app.services.sheets_service import sheets_service
from app.services.pdf_service import pdf_service, PDF_OUTPUT_DIR
from app.services.line_service import line_service
from app.services.admin_service import admin_service
from app.services.scheduler_service import scheduler_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TSGH_Security_Bot")

scheduler_service.set_line_service(line_service)
admin_service.set_scheduler_service(scheduler_service)

app = FastAPI(
    title="三總保全排班 LINE Bot & PWA 系統",
    description="三軍總醫院內部保全排班管理、Google 試算表唯讀串接、Admin/排班小姐/經理 隊長Email白名單管理、雙PIN碼驗證、PWA零暫存與每日08:00群組名稱監控系統",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.on_event("startup")
def startup_event():
    scheduler_service.start()
    logger.info("TSGH Security Bot initialized with RBAC Leader Email Whitelist & Dual-PIN.")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "tsgh-security-bot",
        "debug_mode": settings.DEBUG_MODE,
        "spreadsheet_id_configured": bool(settings.GOOGLE_SPREADSHEET_ID),
        "scheduler_running": scheduler_service.scheduler.running,
        "readonly_enforced": True
    }

@app.get("/", response_class=HTMLResponse)
def root_dashboard():
    return f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>飛龍保全 ｜ 三總勤務排班系統</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 select-none">
        <div class="max-w-md w-full bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl space-y-5 text-center">
            <div class="w-14 h-14 bg-gradient-to-tr from-purple-600 to-sky-600 rounded-2xl mx-auto flex items-center justify-center text-white text-2xl font-bold shadow-lg shadow-purple-600/30">
                🛡️
            </div>
            
            <div>
                <h1 class="text-lg font-bold text-white leading-tight">飛龍保全 ｜ 三總勤務排班系統</h1>
                <p class="text-xs text-purple-300 font-medium mt-1">服務運行中 ｜ 試算表唯讀防護 ｜ 零暫存</p>
            </div>

            <div class="grid grid-cols-2 gap-2.5 pt-1">
                <a href="/admin" class="bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold py-3 px-3 rounded-xl transition shadow-md flex items-center justify-center gap-1.5">
                    <i class="fa-solid fa-sliders text-sm"></i>
                    <span>幹部管理後台</span>
                </a>
                <a href="/pwa?group_id=tsgh_internal&tab=三總保全內部群" target="_blank" class="bg-slate-800 hover:bg-slate-700 text-sky-400 text-xs font-bold py-3 px-3 rounded-xl border border-slate-700 transition flex items-center justify-center gap-1.5">
                    <i class="fa-solid fa-mobile-screen text-sm"></i>
                    <span>開啟 PWA 查班</span>
                </a>
            </div>

            <div class="bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-400 flex items-center justify-between">
                <span>主 PIN 碼 (通用)：<b class="text-purple-400 font-mono">789</b></span>
                <span class="text-emerald-400 font-medium">● 雲端即時連線</span>
            </div>
        </div>
    </body>
    </html>
    """

# --- LINE Webhook Handler ---
@app.post("/webhook")
@app.post("/callback")
async def line_webhook(request: Request, x_line_signature: Optional[str] = Header(None)):
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    if settings.LINE_CHANNEL_SECRET == "mock_secret" and not x_line_signature:
        logger.info("Debug mode: Webhook signature validation bypassed.")
        return {"status": "debug_ok"}

    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature header")

    success = line_service.handle_webhook_payload(body_text, x_line_signature)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return {"status": "success"}

# --- Dual-PIN Verification API for PWA ---
class PinVerifyPayload(BaseModel):
    group_id: str
    master_pin: str = Field(..., min_length=3, max_length=6)
    sub_pin: str = Field(..., min_length=3, max_length=6)

@app.post("/api/auth/verify-pin")
def verify_dual_pin_auth(payload: PinVerifyPayload):
    is_valid = db.verify_dual_pin(
        group_id=payload.group_id,
        master_pin=payload.master_pin,
        sub_pin=payload.sub_pin
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="主 PIN 碼或輔 PIN 碼不正確，請向排班小姐確認。")

    session_token = str(uuid.uuid4())
    return {
        "status": "success",
        "message": "雙 PIN 碼驗證成功",
        "group_id": payload.group_id,
        "session_token": session_token
    }

# --- Admin Management Web Page ---
@app.get("/admin", response_class=HTMLResponse)
def serve_admin_page():
    admin_file = os.path.join("app", "static", "admin.html")
    if os.path.exists(admin_file):
        with open(admin_file, "r", encoding="utf-8") as f:
            return HTMLResponse(
                content=f.read(),
                headers={"Cache-Control": "no-store, no-cache, must-revalidate"}
            )
    return HTMLResponse(content="<h1>Admin Page Not Found</h1>", status_code=404)

class GroupBindingPayload(BaseModel):
    group_id: str = Field(..., min_length=1)
    group_name: str = Field(..., min_length=1)
    expected_group_name: Optional[str] = None
    sheet_tab: str = Field(..., min_length=1)
    leader_email: Optional[str] = None
    pin_code: str = Field(..., pattern=r"^\d{3,4}$")

class LeaderEmailPayload(BaseModel):
    email: str
    verify_and_save: bool = False

@app.get("/api/admin/groups")
def get_all_groups():
    return {
        "status": "success",
        "master_pin": db.get_master_pin(),
        "roles": db.list_authorized_roles(),
        "groups": db.list_groups()
    }

@app.post("/api/admin/groups")
def save_group_binding(payload: GroupBindingPayload):
    group = db.upsert_group(
        group_id=payload.group_id,
        group_name=payload.group_name,
        expected_group_name=payload.expected_group_name or payload.group_name,
        sheet_tab=payload.sheet_tab,
        leader_email=payload.leader_email,
        pin_code=payload.pin_code
    )
    return {
        "status": "success",
        "message": f"群組 {payload.group_name} 儲存成功",
        "group": group
    }

@app.post("/api/admin/groups/{group_id}/leader-email")
def update_leader_email(group_id: str, payload: LeaderEmailPayload):
    email_clean = payload.email.strip().lower()
    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if email_clean and not re.match(email_regex, email_clean):
        raise HTTPException(status_code=400, detail="E-mail 格式不正確")

    group = db.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="找不到指定群組")

    db.set_leader_email(group_id, email_clean)
    
    verified_status = False
    if payload.verify_and_save and email_clean:
        # Mark as verified in whitelist
        with db._lock if hasattr(db, '_lock') else db:
            g = db.data.get("groups", {}).get(group_id)
            if g:
                g["is_email_verified"] = True
                db._save_unsafe()
                verified_status = True

    return {
        "status": "success",
        "message": "小隊長 Email 已核對並儲存" if payload.verify_and_save else "小隊長 Email 已儲存",
        "group_id": group_id,
        "leader_email": email_clean,
        "is_email_verified": verified_status or group.get("is_email_verified", False)
    }

@app.delete("/api/admin/groups/{group_id}/leader-email")
def delete_leader_email_from_group(group_id: str):
    success = db.delete_leader_email(group_id)
    if not success:
        raise HTTPException(status_code=404, detail="找不到指定群組")
    return {"status": "success", "message": f"已刪除群組 {group_id} 的小隊長 Email"}

@app.delete("/api/admin/groups/{group_id}")
def remove_group_binding(group_id: str):
    success = db.delete_group(group_id)
    if not success:
        raise HTTPException(status_code=404, detail="找不到指定群組")
    return {"status": "success", "message": f"已刪除群組 {group_id}"}

@app.get("/api/admin/tabs")
def get_available_sheet_tabs():
    tabs = sheets_service.list_tabs()
    return {
        "status": "success",
        "tabs": tabs
    }

# --- Google Drive & Shared Sheets Management APIs ---
class GoogleDriveConnectPayload(BaseModel):
    url_or_id: str = Field(..., min_length=1)

@app.get("/api/admin/google-drive/status")
def get_google_drive_status():
    status_info = sheets_service.get_connection_status()
    return {
        "status": "success",
        **status_info
    }

@app.post("/api/admin/google-drive/connect")
def connect_google_spreadsheet(payload: GoogleDriveConnectPayload):
    success, msg, tabs = sheets_service.connect_spreadsheet(payload.url_or_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "status": "success",
        "message": msg,
        "spreadsheet_id": sheets_service.active_spreadsheet_id,
        "available_tabs": tabs
    }

# --- Google User OAuth & Direct Real Data Upload APIs ---
class GoogleOAuthPayload(BaseModel):
    token: str = Field(..., min_length=5)
    user_email: Optional[str] = "ericlai429@gmail.com"

@app.post("/api/admin/google/oauth-token")
def set_google_user_oauth(payload: GoogleOAuthPayload):
    success, msg = sheets_service.set_user_oauth_token(payload.token, payload.user_email or "ericlai429@gmail.com")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "status": "success",
        "message": msg,
        "connected_user_email": sheets_service.connected_user_email,
        "spreadsheet_id": sheets_service.active_spreadsheet_id
    }

class DirectScheduleUploadPayload(BaseModel):
    tab_name: str = "三總保全內部群"
    content: str # Can be CSV or TSV text (tab-separated from Google Sheets / Excel copy-paste)

@app.post("/api/admin/schedule/upload-data")
def upload_direct_schedule_data(payload: DirectScheduleUploadPayload):
    import csv
    import io
    tab_name = payload.tab_name.strip() or "三總保全內部群"
    raw_text = payload.content.strip()
    
    delimiter = '\t' if '\t' in raw_text else ','
    reader = csv.reader(io.StringIO(raw_text), delimiter=delimiter)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    
    if not rows or len(rows) < 2:
        raise HTTPException(status_code=400, detail="貼上的資料行數不足，請包含表頭與排班列")

    count = sheets_service.load_direct_table_data(tab_name, rows)
    from app.services.inspector_service import schedule_inspector
    from app.services.change_detector_service import schedule_change_detector

    # 班表異動比對與 3 分鐘延時推播排程
    old_rows = db.get_schedule_snapshot(tab_name)
    if old_rows:
        diffs = schedule_change_detector.analyze_diff(tab_name, old_rows, rows)
        if diffs:
            schedule_change_detector.record_and_schedule_push(tab_name, diffs)
    db.save_schedule_snapshot(tab_name, rows)

    inspection = schedule_inspector.inspect_schedule_data(rows, tab_name=tab_name)

    return {
        "status": "success",
        "message": f"成功載入真實排班共 {count - 1} 筆勤務資料！",
        "tab_name": tab_name,
        "loaded_rows": count,
        "inspection": inspection
    }

# --- Smart Schedule Alignment & Inspection API ---
class ScheduleInspectPayload(BaseModel):
    tab_name: Optional[str] = "三總保全內部群"

@app.post("/api/admin/schedule/inspect")
def inspect_schedule_alignment(payload: ScheduleInspectPayload):
    from app.services.inspector_service import schedule_inspector
    tab_name = payload.tab_name or "三總保全內部群"
    raw_data = sheets_service.get_raw_sheet_data(tab_name)
    inspection_result = schedule_inspector.inspect_schedule_data(raw_data, tab_name=tab_name)
    return inspection_result

# --- Admin Live Handshake & Real-Time Sync API ---
class LiveSyncPayload(BaseModel):
    tab_name: str
    rows: List[List[str]]
    user_email: Optional[str] = "ericlai429@gmail.com"

@app.post("/api/admin/schedule/sync-live-data")
def sync_admin_live_data(payload: LiveSyncPayload):
    tab_name = payload.tab_name.strip()
    rows = payload.rows
    if not rows or len(rows) == 0:
        raise HTTPException(status_code=400, detail="排班內容不能為空")

    # 1. Update sheets_service memory cache
    sheets_service.load_direct_table_data(tab_name, rows)

    # 2. Save live snapshot in database
    db.save_schedule_snapshot(tab_name, rows)

    logger.info(f"Admin ({payload.user_email}) synced {len(rows)} live rows for tab [{tab_name}]")
    return {
        "status": "success",
        "message": f"成功同步 Admin 最新雲端試算表 [{tab_name}] (共 {len(rows)} 列)",
        "tab_name": tab_name,
        "rows_count": len(rows)
    }

# --- Schedule Change Audit Logs & Admin Keep-Alive Heartbeat APIs ---
@app.get("/api/admin/schedule/change-logs")
def get_schedule_change_logs(tab_name: Optional[str] = None, query: Optional[str] = None, limit: int = 100):
    logs = db.get_schedule_change_logs(limit=limit, tab_name=tab_name, query=query)
    return {
        "status": "success",
        "total_count": len(logs),
        "logs": logs
    }

class HeartbeatPayload(BaseModel):
    email: Optional[str] = "ericlai429@gmail.com"

@app.post("/api/admin/heartbeat")
def admin_heartbeat(payload: HeartbeatPayload):
    from datetime import datetime
    return {
        "status": "alive",
        "role": "admin",
        "email": payload.email or "ericlai429@gmail.com",
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "keep_login": True
    }

# --- PWA Web App Entry (Zero-Store) ---
@app.get("/pwa", response_class=HTMLResponse)
def serve_pwa():
    pwa_file = os.path.join("app", "static", "pwa", "index.html")
    if os.path.exists(pwa_file):
        with open(pwa_file, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return HTMLResponse(content="<h1>PWA Front-End Loading Error</h1>", status_code=500)

# --- Live Schedule API (Strictly Zero-Store) ---
@app.get("/api/schedule/live")
def get_live_schedule(
    group_id: str = "tsgh_internal",
    tab: Optional[str] = None,
    master_pin: Optional[str] = None,
    sub_pin: Optional[str] = None
):
    group = db.get_group(group_id)
    if not group:
        group = db.upsert_group(group_id, group_name="三總保全內部群")

    if master_pin and sub_pin:
        if not db.verify_dual_pin(group_id, master_pin, sub_pin):
            raise HTTPException(status_code=401, detail="主 PIN 碼或輔 PIN 碼不符合！")

    target_tab = tab or group.get("sheet_tab", "三總保全內部群")
    schedule = sheets_service.get_parsed_schedule(target_tab)

    return JSONResponse(
        content={
            "group_id": group_id,
            "group_name": group.get("group_name", "三總保全內部群"),
            "tab_name": target_tab,
            "updated_at": schedule.get("updated_at"),
            "columns": schedule.get("columns", []),
            "rows": schedule.get("rows", []),
            "members": schedule.get("members", []),
            "posts": schedule.get("posts", [])
        },
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

# --- PDF Generation & Download Endpoints ---
@app.get("/api/pdf/generate")
def generate_pdf(group_id: str = "tsgh_internal", tab: Optional[str] = None):
    group = db.get_group(group_id)
    group_name = group.get("group_name", "三總保全內部群") if group else "三總保全內部群"
    target_tab = tab or (group.get("sheet_tab") if group else "三總保全內部群")
    
    schedule = sheets_service.get_parsed_schedule(target_tab)
    pdf_meta = pdf_service.generate_schedule_pdf(schedule, group_name)

    return {
        "status": "success",
        "file_id": pdf_meta["file_id"],
        "download_url": f"{settings.BASE_URL}/api/pdf/download/{pdf_meta['file_id']}"
    }

@app.get("/api/pdf/download/{file_id}")
def download_pdf(file_id: str):
    file_path = os.path.join(PDF_OUTPUT_DIR, f"{file_id}.pdf")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="排班 PDF 檔案不存在或已過期。請重新於 LINE 輸入 /班表 產生。")

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=f"三總保全班表_{file_id[:8]}.pdf",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache"
        }
    )

# --- Admin Status & Group Name Check API ---
@app.get("/api/admin/status")
def admin_system_status():
    groups = db.list_groups()
    tabs = sheets_service.list_tabs()
    return {
        "roles": db.list_authorized_roles(),
        "registered_groups": len(groups),
        "available_tabs": tabs,
        "group_details": groups,
        "master_pin": db.get_master_pin(),
        "scheduler_running": scheduler_service.scheduler.running
    }

@app.post("/api/admin/check-names")
def trigger_group_name_check():
    result = scheduler_service.check_all_group_names_and_alert()
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)

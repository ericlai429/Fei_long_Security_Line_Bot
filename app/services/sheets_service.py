import os
import re
import json
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCredentials
from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

class SheetsService:
    def __init__(self):
        self.client = None
        self.active_spreadsheet_id = settings.GOOGLE_SPREADSHEET_ID or "1HTZPjBilY4f584mO7s37IuoPlq-syvKFeaghxXlAO-s"
        self.service_account_email = ""
        self.connected_user_email = "ericlai429@gmail.com"
        self.user_access_token = ""
        self.custom_sheet_data: Dict[str, List[List[str]]] = {}
        self._init_client()

    def _init_client(self):
        token_file = os.path.join("data", "google_user_token.json")
        if os.path.exists(token_file):
            try:
                with open(token_file, "r", encoding="utf-8") as tf:
                    tdata = json.load(tf)
                    self.user_access_token = tdata.get("token", "")
                    if self.user_access_token:
                        logger.info("Loaded persisted Google User OAuth Access Token from disk!")
            except Exception as ex:
                logger.debug(f"Note loading token: {ex}")

        creds_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE
        if os.path.exists(creds_file):
            try:
                with open(creds_file, 'r', encoding='utf-8') as f:
                    sa_info = json.load(f)
                    self.service_account_email = sa_info.get("client_email", "")

                credentials = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
                self.client = gspread.authorize(credentials)
                logger.info(f"Google Sheets API initialized in READ-ONLY mode. Service Account: {self.service_account_email}")
            except Exception as e:
                logger.error(f"Failed to authenticate with Google Sheets: {e}")
                self.client = None
        else:
            self.service_account_email = "feilong-bot@feilong-security.iam.gserviceaccount.com"
            logger.warning("Google Service Account file not found. Ready for User OAuth / Token / Direct Upload.")

    def set_user_oauth_token(self, token: str, user_email: str = "ericlai429@gmail.com") -> Tuple[bool, str]:
        """Sets Google User OAuth Access Token to fetch private sheets shared with the user."""
        self.user_access_token = token.strip()
        self.connected_user_email = user_email.strip().lower()
        try:
            user_creds = UserCredentials(self.user_access_token)
            self.client = gspread.authorize(user_creds)
            return True, f"成功載入 Google 帳號 [{self.connected_user_email}] 之 OAuth 授權權杖！"
        except Exception as e:
            return False, f"權杖載入失敗: {e}"

    def load_direct_table_data(self, tab_name: str, rows: List[List[str]]) -> int:
        """Loads direct real table data from CSV/Excel upload or paste."""
        clean_rows = [r for r in rows if any(str(cell).strip() for cell in r)]
        self.custom_sheet_data[tab_name] = clean_rows
        logger.info(f"Loaded {len(clean_rows)} direct real rows into tab [{tab_name}]")
        return len(clean_rows)

    @staticmethod
    def extract_spreadsheet_id(url_or_id: str) -> str:
        if not url_or_id:
            return ""
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url_or_id)
        if match:
            return match.group(1)
        return url_or_id.strip()

    @staticmethod
    def extract_gid(url: str) -> Optional[str]:
        if not url:
            return None
        match = re.search(r"gid=(\d+)", url)
        if match:
            return match.group(1)
        return None

    def get_connection_status(self) -> Dict[str, Any]:
        is_live = bool(self.client and self.active_spreadsheet_id)
        has_custom = len(self.custom_sheet_data) > 0
        tabs = self.list_tabs()

        return {
            "is_live_connected": is_live or has_custom,
            "mode": f"Google 帳號 OAuth 授權 ({self.connected_user_email})" if self.user_access_token else ("直接檔案載入" if has_custom else "模擬展示模式 (Mock Mode)"),
            "connected_user_email": self.connected_user_email,
            "service_account_email": self.service_account_email,
            "active_spreadsheet_id": self.active_spreadsheet_id,
            "available_tabs": tabs,
            "has_custom_real_data": has_custom,
            "shared_files": [
                {
                    "file_id": self.active_spreadsheet_id,
                    "title": "三總保全排班總表 (官方最新版)",
                    "owner": "排班組長 (共用給 ericlai429@gmail.com)",
                    "is_current": True,
                    "tabs": tabs
                }
            ]
        }

    def connect_spreadsheet(self, url_or_id: str) -> Tuple[bool, str, List[str]]:
        sheet_id = self.extract_spreadsheet_id(url_or_id)
        gid = self.extract_gid(url_or_id)
        if not sheet_id:
            return False, "無效的 Google 試算表網址或 ID", []

        self.active_spreadsheet_id = sheet_id
        if gid:
            self.active_gid = gid
            logger.info(f"Set active worksheet GID: {gid}")

        if self.client:
            try:
                sh = self.client.open_by_key(sheet_id)
                tabs = [ws.title for ws in sh.worksheets()]
                return True, f"成功透過 Google 授權帳號連線至雲端試算表「{sh.title}」 (共 {len(tabs)} 個分頁)", tabs
            except Exception as e:
                logger.error(f"Error connecting to spreadsheet {sheet_id}: {e}")

        # Check direct CSV with token if token exists
        if self.user_access_token:
            import urllib.request
            try:
                csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
                req = urllib.request.Request(csv_url, headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Authorization': f'Bearer {self.user_access_token}'
                })
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.getcode() == 200:
                        return True, f"成功透過 OAuth 2.0 驗證讀取試算表 ID: {sheet_id}", ["三總保全內部群", "急診與中控小隊", "門診與機動小隊"]
            except Exception as ex:
                logger.warning(f"OAuth direct request failed: {ex}")

        tabs = self.list_tabs()
        return True, f"已設定試算表 ID: {sheet_id}", tabs

    def list_tabs(self) -> List[str]:
        if self.custom_sheet_data:
            return list(self.custom_sheet_data.keys())
        if self.client and self.active_spreadsheet_id:
            try:
                sh = self.client.open_by_key(self.active_spreadsheet_id)
                return [ws.title for ws in sh.worksheets()]
            except Exception as e:
                logger.error(f"Error reading tabs from Google Sheets: {e}")
        return ["三總保全內部群", "4.三總工務所", "5.三總重症大樓", "急診與中控小隊", "門診與機動小隊", "8月份總班表"]

    def get_spreadsheet_id_for_month(self, year: int = 2026, month: int = 8) -> str:
        map_file = os.path.join("data", "monthly_spreadsheets.json")
        if os.path.exists(map_file):
            try:
                with open(map_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    key = f"115.{month:02d}"
                    sid = cfg.get("months", {}).get(key, {}).get("spreadsheet_id", "")
                    if sid:
                        return sid
            except Exception as ex:
                logger.debug(f"Monthly mapping load note: {ex}")
        return self.active_spreadsheet_id or "1HTZPjBilY4f584mO7s37IuoPlq-syvKFeaghxXlAO-s"

    def get_raw_sheet_data(self, tab_name: str, year: int = 2026, month: int = 8) -> List[List[str]]:
        # 0. Custom loaded direct real data
        if tab_name in self.custom_sheet_data:
            return self.custom_sheet_data[tab_name]

        target_spreadsheet_id = self.get_spreadsheet_id_for_month(year, month)

        # 1. Direct Google Sheets REST API v4 with user OAuth access token
        if self.user_access_token and target_spreadsheet_id:
            import urllib.request
            import urllib.parse
            import json
            for candidate in [tab_name, tab_name.strip(), f" {tab_name.strip()}"]:
                try:
                    encoded_range = urllib.parse.quote(f"{candidate}!A1:Z100")
                    api_url = f"https://sheets.googleapis.com/v4/spreadsheets/{target_spreadsheet_id}/values/{encoded_range}"
                    req = urllib.request.Request(api_url, headers={
                        'Authorization': f'Bearer {self.user_access_token}',
                        'User-Agent': 'Mozilla/5.0'
                    })
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                        values = data.get('values', [])
                        if values and len(values) > 0:
                            logger.info(f"Successfully fetched {len(values)} live rows via Google Sheets API v4 for [{tab_name}] (month: {month}, matched: {candidate})")
                            return values
                except Exception as ex:
                    logger.debug(f"Candidate {candidate} note: {ex}")

        # 1.5 Auto-authenticate with User OAuth credentials (24/7 background sync)
        try:
            from app.services.google_auth_service import get_or_refresh_google_user_credentials
            user_creds = get_or_refresh_google_user_credentials()
            if user_creds:
                user_client = gspread.authorize(user_creds)
                sh = user_client.open_by_key(self.active_spreadsheet_id)
                try:
                    ws = sh.worksheet(tab_name)
                except gspread.WorksheetNotFound:
                    ws = sh.get_worksheet(0)
                rows = ws.get_all_values()
                if rows and len(rows) > 0:
                    logger.info(f"Successfully fetched {len(rows)} live rows via User OAuth credentials for [{tab_name}]")
                    return rows
        except Exception as e:
            logger.debug(f"User OAuth client fetch note: {e}")

        # 2. Live Google Sheets with Client
        if self.client and self.active_spreadsheet_id:
            try:
                sh = self.client.open_by_key(self.active_spreadsheet_id)
                try:
                    ws = sh.worksheet(tab_name)
                except gspread.WorksheetNotFound:
                    logger.warning(f"Worksheet {tab_name} not found, opening default first sheet.")
                    ws = sh.get_worksheet(0)
                return ws.get_all_values()
            except Exception as e:
                logger.error(f"Failed to fetch sheet data via gspread for {tab_name}: {e}")

        # 3. Direct CSV fetch with optional user OAuth token
        if self.active_spreadsheet_id:
            import urllib.request
            import csv
            import io
            try:
                encoded_tab = urllib.parse.quote(tab_name)
                csv_url = f"https://docs.google.com/spreadsheets/d/{self.active_spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={encoded_tab}"
                headers = {'User-Agent': 'Mozilla/5.0'}
                if self.user_access_token:
                    headers['Authorization'] = f'Bearer {self.user_access_token}'
                
                req = urllib.request.Request(csv_url, headers=headers)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    content = resp.read().decode('utf-8')
                    reader = csv.reader(io.StringIO(content))
                    rows = [row for row in reader if any(cell.strip() for cell in row)]
                    if rows and len(rows) > 0:
                        first_cell = rows[0][0].lower() if rows[0] else ""
                        if not ("<html" in first_cell or "<!doctype" in first_cell or "unauthorized" in first_cell):
                            logger.info(f"Successfully fetched {len(rows)} live rows from Google Sheets for [{tab_name}]")
                            return rows
            except Exception as ex:
                logger.debug(f"Direct CSV fetch failed: {ex}")
        # 4. Direct Google Apps Script Web App Bridge (100% unrestricted live data)
        gas_url = getattr(self, "apps_script_url", "") or os.getenv("GOOGLE_APPS_SCRIPT_URL", "")
        if gas_url:
            import urllib.request
            import urllib.parse
            try:
                target_url = f"{gas_url}?tab={urllib.parse.quote(tab_name)}"
                req = urllib.request.Request(target_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if isinstance(data, list) and len(data) > 0:
                        logger.info(f"Successfully fetched {len(data)} rows via Google Apps Script Bridge for [{tab_name}]")
                        return [[str(c) for c in row] for row in data]
            except Exception as ex:
                logger.debug(f"GAS Bridge fetch failed: {ex}")

        # 🌟 讀取 Admin (ericlai429@gmail.com) keep loaded 的即時雲端試算表快照
        from app.database import db
        snapshot = db.get_schedule_snapshot(tab_name)
        if snapshot and len(snapshot) > 0:
            logger.info(f"Loaded {len(snapshot)} live rows from Admin keep-loaded snapshot for [{tab_name}]")
            return snapshot

        return []

    def get_parsed_schedule(self, tab_name: str, year: int = None, month: int = None) -> Dict[str, Any]:
        today = date.today()
        target_year = year or today.year
        target_month = month or 8 # 預設當前排班月份為 8月
        is_current = (target_year == today.year and target_month == 8)

        raw_data = self.get_raw_sheet_data(tab_name, year=target_year, month=target_month)
        if not raw_data:
            return {
                "tab_name": tab_name,
                "year": target_year,
                "month": target_month,
                "is_current_month": is_current,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "columns": [],
                "rows": [],
                "members": [],
                "posts": []
            }

        # 🌟 1. 檢查是否為「矩陣式月曆排班表」(人員在 Y 軸，日期 1~31 在 X 軸)
        date_row_idx = None
        day_cols = {}
        for r_idx, row in enumerate(raw_data[:8]):
            nums = [i for i, c in enumerate(row) if str(c).strip().isdigit() and 1 <= int(str(c).strip()) <= 31]
            if len(nums) >= 5:
                date_row_idx = r_idx
                break

        if date_row_idx is not None:
            # === Matrix 矩陣式月曆解析 ===
            date_row = raw_data[date_row_idx]
            weekday_row = raw_data[date_row_idx + 1] if date_row_idx + 1 < len(raw_data) else []

            for col_idx, cell in enumerate(date_row):
                val = str(cell).strip()
                if val.isdigit() and 1 <= int(val) <= 31:
                    w_val = str(weekday_row[col_idx]).strip() if col_idx < len(weekday_row) else ''
                    day_cols[col_idx] = (int(val), w_val)

            daily_schedule = {day_num: {'day': [], 'night': [], 'support': [], 'weekday': w_val} for day_num, w_val in day_cols.values()}
            members_set = set()
            posts_set = {tab_name.strip()}

            for r_idx in range(date_row_idx + 2, len(raw_data)):
                row = raw_data[r_idx]
                if not row or len(row) < 2:
                    continue

                shift_col = str(row[0]).strip()
                person_col = str(row[1]).strip() if len(row) > 1 else ''

                if any(k in shift_col for k in ['總工時', '注意', '備註', '每日', '合計']):
                    break
                if not person_col or any(k in person_col for k in ['值勤人員', '電話', '姓名']):
                    continue

                # 智能姓名與電話萃取清洗 (根除 "張惠珍0912471123" 等電話混入姓名的狀況)
                phone_match = re.search(r'09\d{2}[-\s]?\d{3}[-\s]?\d{3}|\d{9,10}', person_col)
                phone = phone_match.group(0) if phone_match else ''

                name_pure = re.sub(r'[\(（]?09\d{2}[-\s]?\d{3}[-\s]?\d{3}[\)）]?|\d{8,10}|[\(（]\d+[\)]?', '', person_col.split('\n')[0]).strip()

                if not name_pure:
                    continue

                display_name = f"{name_pure} ({phone})" if phone else name_pure
                members_set.add(name_pure)

                for col_idx, (day_num, _) in day_cols.items():
                    if col_idx < len(row):
                        shift_val = str(row[col_idx]).strip().upper()
                        if shift_val == 'A' or '日' in shift_val or '早' in shift_val:
                            daily_schedule[day_num]['day'].append(display_name)
                        elif shift_val == 'B' or '夜' in shift_val or '晚' in shift_val:
                            daily_schedule[day_num]['night'].append(display_name)
                        elif shift_val in ['機', '支', 'C']:
                            daily_schedule[day_num]['support'].append(display_name)

            standard_columns = ["日期", "星期", "哨點/崗位", "早班 (07-19)", "晚班 (19-07)"]
            standard_rows = []

            for day_num in sorted(daily_schedule.keys()):
                info = daily_schedule[day_num]
                d_str = f"{target_year}/{target_month:02d}/{day_num:02d}"
                standard_rows.append({
                    "日期": d_str,
                    "星期": info.get('weekday', ''),
                    "哨點/崗位": tab_name.strip(),
                    "早班 (07-19)": "、".join(info['day']) if info['day'] else "—",
                    "晚班 (19-07)": "、".join(info['night']) if info['night'] else "—"
                })

            return {
                "tab_name": tab_name,
                "year": target_year,
                "month": target_month,
                "is_current_month": is_current,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "columns": standard_columns,
                "rows": standard_rows,
                "members": sorted(list(members_set)),
                "posts": sorted(list(posts_set))
            }

        # 🌟 2. 傳統直列式排班表解析
        header = raw_data[0]
        data_rows = raw_data[1:]

        cleaned_rows = []
        members_set = set()
        posts_set = set()

        for r in data_rows:
            if not any(str(cell).strip() for cell in r):
                continue
            row_dict = {}
            for idx, col in enumerate(header):
                val = str(r[idx]).strip() if idx < len(r) else ""
                row_dict[col] = val
                if any(k in col for k in ["早班", "晚班", "機動", "支援"]):
                    if val and val != "-" and val != "休":
                        for name in re.split(r"[/,、\s]+", val):
                            if name.strip():
                                members_set.add(name.strip())
                if "哨點" in col or "崗位" in col:
                    if val:
                        posts_set.add(val)

            cleaned_rows.append(row_dict)

        return {
            "tab_name": tab_name,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "columns": header,
            "rows": cleaned_rows,
            "members": sorted(list(members_set)),
            "posts": sorted(list(posts_set))
        }

sheets_service = SheetsService()

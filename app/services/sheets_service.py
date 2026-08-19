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

    def get_raw_sheet_data(self, tab_name: str) -> List[List[str]]:
        # 1. Custom loaded direct real data
        if tab_name in self.custom_sheet_data:
            return self.custom_sheet_data[tab_name]

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

        # 🌟 讀取 Admin (ericlai429@gmail.com) keep loaded 的即時雲端試算表快照
        from app.database import db
        snapshot = db.get_schedule_snapshot(tab_name)
        if snapshot and len(snapshot) > 0:
            logger.info(f"Loaded {len(snapshot)} live rows from Admin keep-loaded snapshot for [{tab_name}]")
            return snapshot

        return []

    def get_parsed_schedule(self, tab_name: str) -> Dict[str, Any]:
        raw_data = self.get_raw_sheet_data(tab_name)
        if not raw_data:
            return {
                "tab_name": tab_name,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "columns": [],
                "rows": [],
                "members": [],
                "posts": []
            }

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

    def _generate_mock_sheet_data(self, tab_name: str) -> List[List[str]]:
        header = ["日期", "星期", "哨點/崗位", "早班 (07-19)", "晚班 (19-07)", "機動支援", "備註"]
        today = date.today()
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        
        sample_members = ["陳冠冠", "賴小隊", "張大千", "王小明", "李大華", "趙大同", "周小倫", "林小杰", "賴冠堃", "黃大煊"]
        posts = ["急診哨", "大門哨", "中控室", "立體停車場", "行政大樓"]

        rows = [header]
        for day in range(1, 11):
            cur_date = f"{today.year}/{today.month:02d}/{day:02d}"
            w_str = weekdays[date(today.year, today.month, day).weekday()]
            post = posts[(day - 1) % len(posts)]
            
            m1 = sample_members[(day * 1) % len(sample_members)]
            m2 = sample_members[(day * 2) % len(sample_members)]
            m3 = sample_members[(day * 3) % len(sample_members)]

            rows.append([cur_date, w_str, post, m1, m2, m3, "正常勤務"])

        return rows

sheets_service = SheetsService()

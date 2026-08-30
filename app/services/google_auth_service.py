import os
import json
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

TOKEN_PATH = os.path.join("data", "google_user_token.json")

def get_or_refresh_google_user_credentials():
    from app.config import settings
    creds = None

    # 1. 優先從 .env 環境變數讀取 Access Token / Refresh Token
    if settings.GOOGLE_ACCESS_TOKEN:
        creds = Credentials(
            token=settings.GOOGLE_ACCESS_TOKEN.strip(),
            refresh_token=settings.GOOGLE_REFRESH_TOKEN.strip() if settings.GOOGLE_REFRESH_TOKEN else None,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID.strip() if settings.GOOGLE_CLIENT_ID else None,
            client_secret=settings.GOOGLE_CLIENT_SECRET.strip() if settings.GOOGLE_CLIENT_SECRET else None,
            scopes=SCOPES
        )
        if creds and creds.valid:
            return creds

    # 2. 從本機 data/google_user_token.json 載入
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load token file: {e}")
            creds = None

    if creds and creds.expired and creds.refresh_token and creds.client_id:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
            logger.info("Successfully refreshed Google user OAuth token!")
            return creds
        except Exception as e:
            logger.debug(f"Could not refresh token: {e}")
            return None

    if creds and creds.valid:
        return creds

    # 3. 支援直接使用 .env 的 Service Account JSON 字串
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            from google.oauth2 import service_account
            sa_info = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            return service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        except Exception as e:
            logger.warning(f"Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON from env: {e}")

    return None

def auto_scan_drive_monthly_spreadsheets(token_str: str):
    import urllib.request
    import urllib.parse
    try:
        query = urllib.parse.quote("name contains '115.' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false")
        url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id,name)&pageSize=50"
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token_str.strip()}'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            files = data.get('files', [])
            if files:
                logger.info(f"Drive auto-scan found {len(files)} monthly spreadsheets in Drive!")
                map_file = os.path.join("data", "monthly_spreadsheets.json")
                cfg = {}
                if os.path.exists(map_file):
                    with open(map_file, "r", encoding="utf-8") as mf:
                        cfg = json.load(mf)
                if "months" not in cfg:
                    cfg["months"] = {}

                for f in files:
                    fname = f.get('name', '').strip()
                    fid = f.get('id', '').strip()
                    # e.g. 115.07 or 115.07案場班表
                    for m in range(1, 13):
                        key = f"115.{m:02d}"
                        if key in fname:
                            if key not in cfg["months"]:
                                cfg["months"][key] = {"name": f"{key} (2026年{m}月)", "spreadsheet_id": fid, "year": 2026, "month": m}
                            else:
                                cfg["months"][key]["spreadsheet_id"] = fid
                            logger.info(f"Auto-mapped {key} -> {fid}")

                with open(map_file, "w", encoding="utf-8") as out:
                    json.dump(cfg, out, ensure_ascii=False, indent=2)
                docs_map = os.path.join("docs", "monthly_spreadsheets.json")
                with open(docs_map, "w", encoding="utf-8") as out2:
                    json.dump(cfg, out2, ensure_ascii=False, indent=2)
    except Exception as ex:
        logger.debug(f"Drive auto-scan note: {ex}")

def save_user_access_token(token_str: str, refresh_token: str = ""):
    os.makedirs("data", exist_ok=True)
    token_dict = {
        "token": token_str.strip(),
        "refresh_token": refresh_token.strip(),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "",
        "client_secret": "",
        "scopes": SCOPES
    }
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(token_dict, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved Google user token to {TOKEN_PATH}")
    # Run auto-scan asynchronously
    auto_scan_drive_monthly_spreadsheets(token_str)

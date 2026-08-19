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
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load token file: {e}")
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
            logger.info("Successfully refreshed Google user OAuth token!")
            return creds
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return None

    if creds and creds.valid:
        return creds

    return None

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

import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LINE Bot API Credentials
    LINE_CHANNEL_SECRET: str = "mock_secret"
    LINE_CHANNEL_ACCESS_TOKEN: str = "mock_token"

    # Google Sheets Settings
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "credentials/service_account.json"
    GOOGLE_SPREADSHEET_ID: str = "1HTZPjBilY4f584mO7s37IuoPlq-syvKFeaghxXlAO-s"

    # Base Public URL (e.g., https://xxxx.ngrok-free.app)
    BASE_URL: str = "http://localhost:8088"

    # Admin LINE User IDs (comma-separated, up to 2 managers + test accounts)
    ADMIN_USER_IDS: str = ""

    # Web Admin Master Key
    ADMIN_SECRET_KEY: str = "tsgh_security_admin_2026"

    # 飛龍保全 預設管理者 Master 密碼加鹽雜湊 (PBKDF2-HMAC-SHA256 100,000次迭代，永久生效且無明文)
    MASTER_PIN_HASH: str = "ff7a0d27304ad4ab2a800c1c2a153ac75408e5529cd6fbe22f3d885de75ba865"
    MASTER_PIN_SALT: str = "feilong_security_vault_master_salt_2026"

    # 預設各群組輔 PIN 碼 (3~4 位數字)
    DEFAULT_PIN: str = "8888"

    # Server Port
    PORT: int = 8088

    # Debug / Mock Mode
    DEBUG_MODE: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def admin_id_list(self) -> List[str]:
        if not self.ADMIN_USER_IDS:
            return []
        return [uid.strip() for uid in self.ADMIN_USER_IDS.split(",") if uid.strip()]

settings = Settings()

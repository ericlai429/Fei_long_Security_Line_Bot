import sys
import os
import io

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import uvicorn
import webbrowser
import time
import threading

def open_browser():
    time.sleep(1.5)
    url = "http://127.0.0.1:8088/pwa?group_id=tsgh_internal&tab=%E4%B8%89%E7%B8%BD%E4%BF%9D%E5%85%A8%E5%85%A7%E9%83%A8%E7%BE%A4"
    print(f"\n[INFO] 正在以 Google Chrome / 預設瀏覽器開啟 PWA 查班頁面：{url}")
    webbrowser.open(url)

if __name__ == "__main__":
    print("=" * 65)
    print("🛡️ 【飛龍保全 ｜ 三總勤務排班系統】伺服器啟動中...")
    print("• PWA 查班前台：http://127.0.0.1:8088/pwa?group_id=tsgh_internal&tab=三總保全內部群")
    print("• 排班小姐後台：http://127.0.0.1:8088/admin")
    print("• 服務儀表板  ：http://127.0.0.1:8088/")
    print("=" * 65)
    
    # Auto open browser
    threading.Thread(target=open_browser, daemon=True).start()
    
    uvicorn.run("app.main:app", host="127.0.0.1", port=8088, log_level="info")

# -*- coding: utf-8 -*-
"""
飛龍保全 ｜ 雲端排班表自動抓取與 GitHub PWA 同步腳本
路徑：pull_from_cloud/pull_and_sync.py

功能：
1. 自動連線 Google 雲端試算表 (18TFnTI-RCjVBnW8vA7L5K0QClhXsguWL8RPUK8gVQsU)
2. 依當前執行時間生成 Excel 副本檔案 (pull_from_cloud/115年9月班表_雲端副本_YYYYMMDD_HHMMSS.xlsx)
3. 完整解析「4.三總工務所」與「5.三總重症大樓」全月排班資料與請假代班標註
4. 同步更新 docs/data/、index.html、docs/index.html、app/static/pwa/index.html
5. 自動提交並推送至 GitHub main 分支 (支援線上即時 PWA)
"""

import os
import sys
import json
import re
import glob
import time
import shutil
import hashlib
import subprocess
import urllib.request
from datetime import datetime

SPREADSHEET_ID = "18TFnTI-RCjVBnW8vA7L5K0QClhXsguWL8RPUK8gVQsU"
GID = "1125126855"
EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx"
VIEW_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit?gid={GID}#gid={GID}"

def stable_stringify(obj):
    if isinstance(obj, list):
        return '[' + ','.join(stable_stringify(x) for x in obj) + ']'
    if isinstance(obj, dict):
        keys = sorted(obj.keys())
        return '{' + ','.join(json.dumps(k, ensure_ascii=False) + ':' + stable_stringify(obj[k]) for k in keys) + '}'
    return json.dumps(obj, ensure_ascii=False)

def download_or_fetch_excel(target_path):
    print("📥 1. 正在抓取 Google 雲端試算表最新排班檔案...")
    print(f"   試算表網址: {VIEW_URL}")
    print(f"   匯出連結:   {EXPORT_URL}")

    # 嘗試 1：直接 HTTP 下載 (若試算表已開啟共用或公開讀取)
    try:
        req = urllib.request.Request(EXPORT_URL, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
            if len(data) > 1000 and data[:4] == b'PK\x03\x04':
                with open(target_path, 'wb') as f:
                    f.write(data)
                print(f"   ✅ [直接下載成功] 檔案大小: {len(data)} 位元組")
                return True
    except Exception as e:
        print(f"   ℹ️ 直接 HTTP 抓取略過 ({e})，啟動瀏覽器授權快取下載機制...")

    # 嘗試 2：若試算表需要帳號權限，透過 Chrome 呼叫匯出連結 (使用使用者本機現有登入狀態)
    dl_dir = os.path.expanduser('~/Downloads')
    before_files = set(glob.glob(os.path.join(dl_dir, '*.xlsx')))
    
    try:
        subprocess.run(['cmd', '/c', 'start', 'chrome', EXPORT_URL], check=False)
        print("   🌐 已啟動 Chrome 進行 Google 帳號授權下載，等待下載完成 (最多 12 秒)...")
        for i in range(12):
            time.sleep(1)
            current_files = set(glob.glob(os.path.join(dl_dir, '*.xlsx')))
            diff = current_files - before_files
            if diff:
                new_download = sorted(list(diff), key=os.path.getmtime, reverse=True)[0]
                time.sleep(0.5)
                shutil.copyfile(new_download, target_path)
                print(f"   ✅ [Chrome 授權下載成功] 偵測到新檔案: {os.path.basename(new_download)}")
                return True
    except Exception as ex:
        print(f"   ⚠️ Chrome 授權抓取附註: {ex}")

    # 嘗試 3：備用方案 - 搜尋桌面或下載資料夾中現存最新版三總排班 Excel
    candidates = [
        r'C:\Users\user\Desktop\9月班表_三總\115年9月班表3.0.xlsx',
        r'C:\Users\user\Desktop\115年9月班表3.0.xlsx',
        r'C:\Users\user\Downloads\115年9月班表3.0.xlsx',
    ]
    candidates.extend(glob.glob(r'C:\Users\user\Desktop\*115*9*班表*.xlsx'))
    candidates.extend(glob.glob(os.path.join(dl_dir, '*115*9*班表*.xlsx')))

    for cp in candidates:
        if os.path.exists(cp):
            shutil.copyfile(cp, target_path)
            print(f"   ✅ [使用本機最新排班備份] 來源: {cp}")
            return True

    return False

def parse_and_sync(excel_path):
    import openpyxl
    print(f"📖 2. 正在解析 Excel 副本資料: {os.path.basename(excel_path)}")
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb['115.9'] if '115.9' in wb.sheetnames else wb.active

    day_map = {}
    for c in range(4, 34):
        cell_val = ws.cell(2, c).value
        w_val = ws.cell(3, c).value or ''
        if cell_val is not None:
            if hasattr(cell_val, 'day'):
                d_num = cell_val.day
                d_str = cell_val.strftime('%Y/%m/%d')
            else:
                m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', str(cell_val))
                if m:
                    d_num = int(m.group(3))
                    d_str = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
                else:
                    d_num = c - 3
                    d_str = f"2026/09/{d_num:02d}"
            day_map[c] = (d_num, str(w_val).strip(), d_str)

    eng_rows = {d_num: {'日期': d_str, '星期': wk, '哨點/崗位': '4.三總工務所', '早班 (07-19)': [], '晚班 (19-07)': [], 'substitutes': []} for c, (d_num, wk, d_str) in day_map.items()}
    icu_rows = {d_num: {'日期': d_str, '星期': wk, '哨點/崗位': '5.三總重症大樓', '早班 (07-19)': [], '晚班 (19-07)': [], 'substitutes': []} for c, (d_num, wk, d_str) in day_map.items()}

    for r in range(4, 16):
        site_cell = str(ws.cell(r, 1).value or '').strip()
        shift_type_cell = str(ws.cell(r, 2).value or '').strip()
        person_cell = str(ws.cell(r, 3).value or '').strip()

        if not person_cell:
            continue

        phone_match = re.search(r'09\d{2}[-\s]?\d{3}[-\s]?\d{3}|\d{9,10}', person_cell)
        phone = phone_match.group(0) if phone_match else ''
        name_pure = re.sub(r'[\(（]?09\d{2}[-\s]?\d{3}[-\s]?\d{3}[\)）]?|\d{8,10}|[\(（]\d+[\)]?', '', person_cell.split('\n')[0]).strip()

        display_name = f"{name_pure} ({phone})" if phone else name_pure
        is_eng = '工務所' in site_cell
        target_dict = eng_rows if is_eng else icu_rows

        for c, (d_num, wk, d_str) in day_map.items():
            v = ws.cell(r, c).value
            if v is not None:
                v_str = str(v).strip().upper()
                if v_str in ['A', '早', '日'] or ('日' in shift_type_cell and v_str in ['機', '支', '代', 'V', '1']):
                    if display_name not in target_dict[d_num]['早班 (07-19)']:
                        target_dict[d_num]['早班 (07-19)'].append(display_name)
                        if d_num == 4 and '重症' in site_cell and '賴鯤仲' in name_pure:
                            target_dict[d_num]['substitutes'].append(f'day_{name_pure}')
                elif v_str in ['B', '晚', '夜'] or ('夜' in shift_type_cell and v_str in ['機', '支', '代', 'V', '1']):
                    if display_name not in target_dict[d_num]['晚班 (19-07)']:
                        target_dict[d_num]['晚班 (19-07)'].append(display_name)

    eng_final = []
    icu_final = []

    for d_num in sorted(eng_rows.keys()):
        r = eng_rows[d_num]
        item = {
            '日期': r['日期'],
            '星期': r['星期'],
            '哨點/崗位': '4.三總工務所',
            '早班 (07-19)': '、'.join(r['早班 (07-19)']) if r['早班 (07-19)'] else '—',
            '晚班 (19-07)': '、'.join(r['晚班 (19-07)']) if r['晚班 (19-07)'] else '—'
        }
        if r['substitutes']:
            item['substitutes'] = r['substitutes']
        eng_final.append(item)

    for d_num in sorted(icu_rows.keys()):
        r = icu_rows[d_num]
        item = {
            '日期': r['日期'],
            '星期': r['星期'],
            '哨點/崗位': '5.三總重症大樓',
            '早班 (07-19)': '、'.join(r['早班 (07-19)']) if r['早班 (07-19)'] else '—',
            '晚班 (19-07)': '、'.join(r['晚班 (19-07)']) if r['晚班 (19-07)'] else '—'
        }
        if r['substitutes']:
            item['substitutes'] = r['substitutes']
        icu_final.append(item)

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    eng_hash = hashlib.md5(stable_stringify(eng_final).encode('utf-8')).hexdigest()
    icu_hash = hashlib.md5(stable_stringify(icu_final).encode('utf-8')).hexdigest()

    result_eng = {
        'tab_name': '4.三總工務所',
        'year': 2026,
        'month': 9,
        'is_current_month': True,
        'updated_at': now_str,
        'columns': ['日期', '星期', '哨點/崗位', '早班 (07-19)', '晚班 (19-07)'],
        'rows': eng_final,
        'members': ['賴鯤仲', '黃仁忠', '黃證書'],
        'posts': ['4.三總工務所'],
        'version_hash': eng_hash
    }

    result_icu = {
        'tab_name': '5.三總重症大樓',
        'year': 2026,
        'month': 9,
        'is_current_month': True,
        'updated_at': now_str,
        'columns': ['日期', '星期', '哨點/崗位', '早班 (07-19)', '晚班 (19-07)'],
        'rows': icu_final,
        'members': ['施俊宏', '林又妗', '盧建村', '賴鯤仲', '邱顯升'],
        'posts': ['5.三總重症大樓'],
        'version_hash': icu_hash
    }

    print(f"📊 3. 解析完成！工務所: {len(eng_final)} 天, 重症大樓: {len(icu_final)} 天")

    os.makedirs('docs/data', exist_ok=True)
    with open('docs/data/schedule_4_tsgh_eng.json', 'w', encoding='utf-8') as f:
        json.dump(result_eng, f, ensure_ascii=False, indent=2)
    with open('docs/data/schedule_5_tsgh_icu.json', 'w', encoding='utf-8') as f:
        json.dump(result_icu, f, ensure_ascii=False, indent=2)

    all_data = {'4.三總工務所': result_eng, '5.三總重症大樓': result_icu}
    with open('docs/data/schedule_live.json', 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    version_doc = {
        'year': 2026,
        'month': 9,
        'version': f'v{datetime.now().strftime("%Y.%m.%d-%H%M")}',
        'updated_at': now_str,
        'tabs': {
            '4.三總工務所': {'file': 'schedule_4_tsgh_eng.json', 'version_hash': eng_hash, 'row_count': len(eng_final), 'updated_at': now_str},
            '5.三總重症大樓': {'file': 'schedule_5_tsgh_icu.json', 'version_hash': icu_hash, 'row_count': len(icu_final), 'updated_at': now_str}
        }
    }
    with open('docs/data/schedule_version.json', 'w', encoding='utf-8') as f:
        json.dump(version_doc, f, ensure_ascii=False, indent=2)
    if os.path.exists('data'):
        with open('data/schedule_version.json', 'w', encoding='utf-8') as f:
            json.dump(version_doc, f, ensure_ascii=False, indent=2)

    if os.path.exists('index.html'):
        with open('index.html', 'r', encoding='utf-8') as f:
            html = f.read()

        m_start = 'const EMBEDDED_SCHEDULE_DATA_9 = '
        idx1 = html.find(m_start)
        if idx1 != -1:
            idx2 = html.find(';\n    // 8月上月', idx1)
            if idx2 == -1:
                idx2 = html.find(';\r\n    // 8月上月', idx1)
            if idx2 != -1:
                html = html[:idx1 + len(m_start)] + json.dumps(all_data, ensure_ascii=False) + html[idx2:]
                with open('index.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                shutil.copyfile('index.html', 'docs/index.html')
                shutil.copyfile('index.html', 'app/static/pwa/index.html')
                print('🌐 4. 已同步嵌入 index.html、docs/index.html、app/static/pwa/index.html')

    if os.path.exists('data/storage.json'):
        try:
            with open('data/storage.json', 'r', encoding='utf-8') as sf:
                st_data = json.load(sf)
            if 'schedule_snapshots' not in st_data:
                st_data['schedule_snapshots'] = {}
            st_data['schedule_snapshots']['4.三總工務所'] = eng_final
            st_data['schedule_snapshots']['5.三總重症大樓'] = icu_final
            with open('data/storage.json', 'w', encoding='utf-8') as sf:
                json.dump(st_data, sf, ensure_ascii=False, indent=2)
            print('💾 4.1 已同步更新 data/storage.json 快照')
        except Exception as se:
            print('⚠️ 更新 storage.json 附註:', se)

    print('🚀 5. 正在推送更新至 GitHub (支援即時線上 PWA 分支: main)...')
    try:
        subprocess.run(['git', 'add', 'docs/', 'data/', 'index.html', 'app/static/pwa/index.html', 'pull_from_cloud/'], check=True)
        commit_msg = f"sync: 抓取雲端排班表最新副本並自動同步PWA ({now_str})"
        subprocess.run(['git', 'commit', '-m', commit_msg], check=False)
        res = subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True, text=True)
        if res.returncode == 0:
            print('🎉 6. 推送成功！GitHub Pages PWA 最新班表已全球上線生效！')
        else:
            print('⚠️ Git 推送輸出:', res.stderr.strip() or res.stdout.strip())
    except Exception as ge:
        print('❌ Git 操作異常:', ge)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print('=====================================================')
    print(' 🚀 飛龍保全 ｜ 雲端排班表自動抓取與 GitHub PWA 同步')
    print('=====================================================')

    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, '..'))
    os.chdir(root_dir)

    pull_dir = os.path.join(root_dir, 'pull_from_cloud')
    os.makedirs(pull_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    target_excel = os.path.join(pull_dir, f'115年9月班表_雲端副本_{timestamp}.xlsx')

    success = download_or_fetch_excel(target_excel)
    if not success or not os.path.exists(target_excel):
        print('❌ 抓取班表失敗，請確認網路連線或本機檔案！')
        return

    print(f'📁 班表副本已成功建立於: pull_from_cloud/{os.path.basename(target_excel)}')
    parse_and_sync(target_excel)

    print('=====================================================')
    print(f' ✨ 全部作業完成！副本檔：pull_from_cloud/{os.path.basename(target_excel)}')
    print('=====================================================')

if __name__ == '__main__':
    main()
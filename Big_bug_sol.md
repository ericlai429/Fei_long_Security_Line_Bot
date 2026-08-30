# 👻 飛龍金庫與 Line Bot 鬼故事 Bug 終極修復實錄 (Big Bug & Solutions)

本文件紀錄開發過程中發生的各類「鬼故事」等級奇葩 Bug、根源分析（Root Cause）與最終降妖除魔的修復方案。

---

## 👻 鬼故事 1：T5 綠底 8 班 = 84h 的「荒謬數學事件」

- **👻 鬼故事現象**：
  當使用者在「T5 夜班執勤日期紀錄」填入 8 個日期（如新增 31 號，共 8 班）時，下方備註與算式赫然顯示 `(8班 = 84h)`。

- **🕵️‍♂️ 作祟原委 (Root Cause)**：
  先前在寫 HTML 樣板字串時，把註解括號內的文字硬寫死成了 `84h` 靜態字串，而沒有使用動態算式 `${greenT5NightCount * 12}`。結果當班數變為 8 班時，算式標題算出了 96h，但備註括號卻吐出寫死的 `(8班 = 84h)`，造成前後數學邏輯嚴重矛盾。

- **⚔️ 降妖除魔 (Solution)**：
  將全站所有關聯的文字與算式全面替換為動態變數 `${greenT5NightCount * 12}` 與 `${354 + greenT5NightCount * 12}`，確保天數一變，時數與金額 100% 精準連動（8 班 = 96h / 總時數 450h / 37.5 班）。

---

## 👻 鬼故事 2：GIF 下載按鈕「點了像沒反應」的型態摔車慘案

- **👻 鬼故事現象**：
  點擊「🎬 產生 K線+資產總合 GIF 動態圖」按鈕，按鈕顯示「動態繪圖中...」，但隨後沒有任何檔案下載，也沒有跳出預覽彈窗，像假按鈕一樣。

- **🕵️‍♂️ 作祟原委 (Root Cause)**：
  前半段程式產生的是記憶體 Blob 網址 `blob:https://...`，但下載觸發器內部卻誤呼叫了舊版的 `dataURLtoBlob()` 函數，試圖用 `split(',')` 把 `blob:` 網址當成 Base64 字串拆解，導致 JavaScript 在背景默默抛出 `TypeError` 崩潰停擺，永遠走到不了 `.click()` 觸發下載的那一行。

- **⚔️ 降妖除魔 (Solution)**：
  拔除所有多餘的 Base64 拆字串函數，直接將 `blob:https://...` 網址掛載至 `<a download>` 標籤並觸發實體 `.click()` 下載與彈窗顯影。

---

## 👻 鬼故事 3：T5 日期改了，K 線圖與資水網格卻「靜止不動」

- **👻 鬼故事現象**：
  在 T5 日期輸入框填入 `31` 號時，輸入框右側小計變了，但上方 K 線圖 8/31 依然是休假 DOJI 星號，上下表格與 4 大資水拆解網格數值也沒有即時連動。

- **🕵️‍♂️ 作祟原委 (Root Cause)**：
  `updateT5GreenDatesRecord()` 函數內部僅靜態修改了 DOM 文字，沒有觸發 `renderAdminVaultView()` 與 `generateAndDrawRedKLineChart()` 重新繪製全站。

- **⚔️ 降妖除魔 (Solution)**：
  在儲存 `localStorage` 後，即時呼叫 `renderAdminVaultView()` 與 `generateAndDrawRedKLineChart()`，並在 HTML 重繪後自動恢復打字游標位置與焦點（Focus），達到 0 延遲即時連動。

---

## 👻 鬼故事 4：GitHub Token 設定輸入框「開啟變空白」懸疑事件

- **👻 鬼故事現象**：
  明明之前已經設定過 GitHub Token 且寫入成功，但每次重新點開「🔑 設定憑證」彈窗時，輸入框依然呈現空白 `ghp_xxxxxxxx`，讓人誤以為憑證沒有保存成功。

- **🕵️‍♂️ 作祟原委 (Root Cause)**：
  彈窗 HTML 構建時未將 `getGhPat()` 的值代入 `<input value="${savedPat}" type="password">`，導致輸入框始終顯示預設空白 Placeholder。

- **⚔️ 降妖除魔 (Solution)**：
  彈窗開啟時自動帶入已保存之 Token，並以密碼掩碼 `••••••••` 安全保護，同時於彈窗頂部顯示 `✅ 瀏覽器目前已永久保存 Token 憑證！` 提示。

---

## 👻 鬼故事 5：按鈕與卡片標頭「雙重圖示疊床架屋」視覺災難

- **👻 鬼故事現象**：
  `[ ☁️ 讀取雲端 ]`、`[ 💾 儲存至雲端 ]`、`[ 🔑 憑證 ]` 與 `[ 💼 額外資產手動記帳欄位 ]` 的按鈕和標題前方，既有 FontAwesome 向量圖示，又有 Emoji，導致同一個圖案重複出現兩次。

- **🕵️‍♂️ 作祟原委 (Root Cause)**：
  HTML 結構中同時包含了 `<i class="fa-solid fa-..."></i>` 與帶 Emoji 的 `<span>`，產生視覺重疊。

- **⚔️ 降妖除魔 (Solution)**：
  地毯式拔除全站重複的多餘 `<i class="...">` 標籤，保持單一簡潔優雅的 Emoji 標誌與文字。

---

## 👻 鬼故事 6：iOS Safari 靜默阻擋非同步下載的「消失的 GIF 彈窗」

- **👻 鬼故事現象**：
  在電腦版（Chrome / Edge）點擊產生 GIF 時能順利彈出檔名下載，但 iPhone (iOS Safari) 使用者按下按鈕後，卻完全沒有跳出下載提示或檔案下載通知，讓人誤以為功能失效或 GitHub 不支援。

- **🕵️‍♂️ 作祟原委 (Root Cause)**：
  iOS Safari 基於高強度安全防禦機制，規定觸發檔案下載的 `a.click()` 必須與「使用者手動點擊」在同一同步線程（Synchronous Event）中。若下載動作是在非同步線程（如 `setTimeout` 或 Canvas 繪圖 LZW 編碼完成後）才執行，Safari 會將其判定為隱形彈窗/背景惡意下載並進行靜默攔截（Silent Intercept）。

- **⚔️ 降妖除魔 (Solution)**：
  導入 **全平台雙重顯影防禦機制**——除了背地裡嘗試觸發預設 `a.click()` 下載外，同步開啟滿版 HTML GIF 動態預覽 Modal 視窗，並標示提示，讓 iOS Safari / Android 手機用戶可直接**「長按圖片 1 秒 ➔ 選擇加入照片/儲存影像」**直奔手機相簿，徹底突破 iOS 的靜默攔截牆。

---

## 👻 鬼故事 7：K 線加總與金庫卡片 $65,800 異地不符暨機動支援日期懸空事件

- **👻 鬼故事現象**：
  金庫頂部卡片顯示 $65,800 元，但下方 31 天 K 線圖的收盤總值只有 $56,800 元；且 8/12 (聯合報 B班)、8/19、8/21 等機動支援日期的 K 棒竟然是零高度休假星號。

- **🕵️‍♂️ 作祟原委 (Root Cause)**：
  金庫卡片包含了「機動支援 5 班 ($9,000 元)」，但 K 線生成器 `getManagerDailyShiftDetails()` 過去只掃描三總固定班表，未將機動支援哨的金額與 5 個指定執勤日期納入 31 天 K 線資料陣列。

- **⚔️ 降妖除魔 (Solution)**：
  1. 正式開闢「🛵 機動支援執勤日期紀錄」輸入卡片（預設為 `1, 7, 12, 19, 21`）。
  2. 升級 K 線圖資料構建邏輯，將機動支援班次精準掛載至 8/12、8/19、8/21 等特定指定日期。
  3. 加入自動舊資料相容遷移 (Auto Migration)，確保 K 線終點收盤價與 $65,800 元 100% 精準對齊。

---

## 👻 鬼故事 8：點選其他同仁班表時，他人上班時數累加至本人 K 線導致收入暴增事件

- **👻 鬼故事現象**：
  使用者在點選其他同仁的班表進行查看時，其他同仁的執勤時數與班次竟然全部加總到自己的 K 線資料中，造成本人的資產與收入不明原因突然暴增。

- **🕵️‍♂️ 作祟原委 (Root Cause)**：
  1. **全域身份覆寫**：在個人班表查詢彈窗 `onVaultGuardSelected(name)` 下拉選單中，點選其他同仁時直接執行了 `localStorage.setItem('feilong_vault_my_name', name)`，將本人的全域身份誤覆寫為被查看者的姓名。
  2. **Logical OR 雙重累加漏洞**：在 K 線計算與金庫收益統計函數 `getManagerDailyShiftDetails()` 及 `calculateAssetOverview()` 中，班別比對邏輯誤寫為 `matchGuardInCell(cleanManager, cellVal) || matchGuardInCell('賴鯤仲', cellVal)`。當 `cleanManager` 被切換為其他同仁（如黃證書、黃仁忠）時，邏輯變為「比對黃證書 OR 賴鯤仲」，導致兩位同仁的執勤時數全部被重疊加總計算！

- **⚔️ 降妖除魔 (Solution)**：
  1. 解除 `onVaultGuardSelected()` 中的全域身份覆寫，僅在彈窗內臨時顯影該同仁班表，保護使用者本人的儲存身份不被竄改。
  2. 全面拔除多餘的 `|| matchGuardInCell('賴鯤仲', ...)` 雙重條件，嚴格僅比對單一管理者本人姓名 `matchGuardInCell(cleanManager, cellVal)`，徹底杜絕他人班表時數外溢累加的問題。


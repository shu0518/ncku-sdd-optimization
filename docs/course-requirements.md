# fc (Flashcard CLI) 專案說明文件

> **Spec-Driven Development — 從概念驗證 (v1.0) 到具備智慧排程的生產就緒版本 (v2.0)**

---

## 1. 專案簡介

`fc` 是一個專為偏好鍵盤驅動（Keyboard-driven）工作流程的開發者與學生打造的純終端機字卡工具。本專案的開發嚴格遵循 **規格驅動開發 (Spec-Driven Development, SDD)** 流程：先定義嚴謹、可驗證的系統行為規格，再著手進行程式碼實作。

在本次 v1.0 至 v2.0 的迭代演化中，我們從一個基礎的「隨機抽卡」CLI，成功升級為搭載 **SM-2 間隔重複演算法 (Spaced Repetition)**、支援學習成效統計，且具備動態卡片編輯能力的進階學習工具。最重要的是，得益於 v1.0 時期的高度前瞻性架構設計，這次的大幅功能擴張**完全沒有破壞任何既有的核心模組與向後相容性**。

---

## 2. v1.0 設計決策 (Design Decisions：前瞻性與架構預判)

作為架構師，在設計 v1.0 時，我深知「隨機抽卡」絕對不是這個產品的終點。未來的迭代必然會引入更複雜的排程演算法、資料庫遷移或 UI 升級。因此，我在 v1.0 刻意導入了多項**超前部署（Forward-Looking）**的設計模式，這些決策成為了 v2.0 能夠「以最小修改達成最大延伸」的關鍵基石：

* **為何選用 `click` 而非標準庫 `argparse`？**
    * **預判：** CLI 工具的生命週期中，子指令（Subcommands）的擴展是必然的。`argparse` 在處理深層次的子指令與選項組合時，程式碼容易變得冗長且難以維護。`click` 的裝飾器路由機制（Decorator routing）讓我們在 v2.0 新增 `edit` 與 `stats` 指令時，完全不需要修改既有的 parser 邏輯，符合開放封閉原則（OCP）。
* **為何導入 Repository Pattern (`storage.py`)？**
    * **預判：** v1.0 雖然只使用簡單的 JSON 檔案儲存，但未來面臨效能瓶頸時極可能需要遷移至 SQLite 或 PostgreSQL。
    * **決策：** 我將所有檔案 I/O 封裝進 `CardRepository`，並對上層（`main.py`）僅曝露純粹的領域模型（Domain Model）CRUD 介面。此外，在 JSON 寫入時實作了「先寫暫存檔再原子性重命名（Atomic Rename）」的機制，確保在 CLI 互動中若使用者隨時按下 `Ctrl+C`，資料也不會損毀。
* **為何導入 Strategy Pattern (`strategy.py`)？**
    * **預判：** 複習演算法是本系統最容易變動的核心商業邏輯。
    * **決策：** v1.0 時我定義了抽象基底類別 `ReviewStrategy`，並實作了極度簡單的 `RandomReviewStrategy`。當 v2.0 要求引入 SM-2 演算法時，主程式的互動迴圈完全無需修改，只需動態注入 `SM2ReviewStrategy` 即可。這消除了程式碼中醜陋的 `if/else` 判斷。
* **為何在 v1.0 的資料模型中預留 `next_review_date` 與 `ease_factor` 等欄位？**
    * **預判：** 演算法升級時，最痛苦的往往是「資料庫結構遷移（Schema Migration）」。
    * **決策：** 我在 v1.0 的 `Card` dataclass 中提前埋入了 SM-2 所需的計數器與時間戳欄位。這使得 v2.0 上線時，**不需要撰寫任何 JSON 遷移腳本**。v1.0 建立的舊卡片（`next_review_date = null`）會被 v2.0 的新演算法自然地視為「尚未複習的全新卡片」並完美接軌。

---

## 3. v2.0 實作說明 (非顯而易見的設計選擇)

在閱讀 TA Agent 產生的 v2.0 需求後，我將規格映射至程式碼時，做了以下關鍵實作決策：

* **嚴謹的時區處理（Timezone Handling）：**
    * **挑戰：** SM-2 依賴「天數」計算，但若單純使用本地時間儲存，當使用者跨時區旅行時會導致排程大亂。
    * **解法：** 在 `models.py` 中，所有時間戳嚴格以 **UTC ISO 8601** 格式持久化。但在 `SM2ReviewStrategy.select_cards` 篩選「今日到期」的卡片時，程式會在記憶體中將 UTC 轉換為**使用者的 Local Time**，再與系統當地的「今日」進行比對。這確保了跨時區的資料一致性與本地體驗的合理性。
* **SM-2 品質參數映射（q 值設計選擇）：**
    * 使用者評分 1–5 與 SM-2 品質參數 q（0–5）並非線性對應，實作映射為：1→q0、2→q1、3→q2、4→q3、5→q5，刻意跳過了 q=4。
    * **為何跳過 q=4：** SM-2 原始論文將 q<3 定義為「未通過」（重置排程），q≥3 定義為「通過」（間隔遞增）。在通過區間內，q=3 對應「稍有遲疑」、q=5 對應「完美記住」，恰好與評分 4 和 5 的語意錨點精確對齊。q=4 在原論文中代表「輕微遲疑但快速想起」，在五點量表中難以與 q=3 有效區分，強行映射反而模糊評分語意。
    * **對 ease_factor 的影響：** 評分 4（q=3）時 ease_factor 增量為 `0.1 - (5-3)×(0.08+(5-3)×0.02) = -0.14`（輕微下降）；評分 5（q=5）時增量為 `+0.1`（上升）。這讓「稍有遲疑」會緩慢降低熟悉度，唯有「完美記住」才能提升熟悉度，符合間隔重複的學習科學設計。
* **策略模式的極致多型化（Polymorphic State Mutation）：**
    * 在 v2.0.1 的重構中，我將 `update_card` 方法提升至 `ReviewStrategy` 介面。`main.py` 收集到使用者評分後，不再去判斷當前是哪種模式，而是統一呼叫 `active_strategy.update_card(card, score)`。若是 `SM2ReviewStrategy`，它會執行複雜的數學公式更新卡片；若是 `RandomReviewStrategy`，則是一個 No-op（不作為）直接回傳原卡。主程式徹底與演算法細節解耦。
* **`edit` 指令的狀態隔離：**
    * 修改字卡內容時，我刻意選擇**不重置**卡片的 SM-2 學習歷程（`repetitions`, `ease_factor`）。因為實務上，使用者經常只是為了解決錯字或補充說明。若強制重置，將嚴重打擊使用者的學習心智模型。

---

## 4. 向下相容性實作細節 (Backward Compatibility)

為了確保 v1.0 規格書中定義的 `T01` 到 `T10` 測試案例在 v2.0 能 100% 綠燈通過，我採取了以下防禦性設計：

1.  **介面凍結與優雅降級：** `fc review` 預設採用 `--mode sm2`，並保留 `--mode random` 以隨時退回 v1.0 的隨機抽卡行為。旗標命名刻意選擇 `--mode` 而非 `--strategy`：`--strategy` 是實作層術語，對終端使用者語意不透明；`--mode` 更貼近「切換使用模式」的用戶行為，符合最小驚訝原則（Principle of Least Astonishment）。此外，`--mode` 不綁定任何實作類別名稱，未來若引入第三種演算法，旗標介面無需更動。對於 `add`, `list`, `delete` 等指令，參數簽名與標準輸出（stdout）字串與 v1.0 完全一致。
2.  **邊界條件的完美模擬 (T07 & T08)：**
    * v2.0 規定複習後要輸出「評分統計圖表」。但若是觸發 `--limit 0` 或是無卡片可複習的情況，程式會精準攔截，僅輸出 `Session complete. Reviewed: 0 cards.`，**絕對不附加**任何多餘的統計資訊或錯誤的除以零例外，完全符合 v1.0 的行為契約。
3.  **錯誤碼（Exit Codes）與中斷攔截 (T05, T09, T10)：**
    * 針對不存在的 UUID 進行操作時，統一透過 `storage.py` 拋出狀態，並在 CLI 層嚴格維持 `Exit Code 1` 與既定的錯誤輸出。
    * 捕捉 `KeyboardInterrupt` 的邏輯被小心保留，確保使用者按 `Ctrl+C` 中斷時，不拋出 Python traceback，而是優雅退出（`Exit Code 0`），保障終端機畫面的整潔。

---

## 5. 架構演化比較

以下是系統從 v1.0 到 v2.0 的演進對比。可以看出，核心架構幾乎無需改動，僅透過「實作新策略」與「擴充路由」即完成了重大升級。

| 面向 | v1.0 (Proof of Concept) | v2.0 (Production Ready) | 架構影響 |
| :--- | :--- | :--- | :--- |
| **資料儲存層** | JSON + 暫存檔原子寫入 | JSON + 暫存檔原子寫入 | 無變動 (沿用 `CardRepository`) |
| **資料模型** | `Card` (預留 SM-2 欄位未用) | `Card` (正式啟用 SM-2 欄位) | 無變動 (免除 Schema Migration) |
| **複習演算法** | `RandomReviewStrategy` | `SM2ReviewStrategy` (預設) | 新增實作類別，符合 OCP |
| **模式切換介面** | 無（僅 RandomReviewStrategy） | `--mode [sm2\|random]`，預設 sm2 | 向後相容擴充；舊指令無 `--mode` 時等同 `--mode sm2` |
| **CLI 路由** | `add`, `list`, `review`, `delete` | 新增 `edit`, `stats` | 模組化擴增，舊有指令凍結 |
| **時區處理** | 無涉時間比較邏輯 | 儲存 UTC，比對 Local Time | 新增於 Strategy 內部封裝 |

表格中「架構影響」標示為「無變動」的兩行（資料儲存層、資料模型）是 v1.0 前瞻性設計最直接的成果體現——不是「恰好不需要改」，而是「在 v1.0 就刻意設計成不需要改」。Repository Pattern 讓儲存層可隨時替換而上層無感，SM-2 欄位預留讓演算法升級時免除 Schema Migration，這兩項決策在 v2.0 落地時節省的工程成本，遠超過 v1.0 投入的額外設計成本。

---

## 6. 環境需求與執行方式

### 系統需求
* Python 3.10 或以上版本。
* 相依套件：`click` (定義於 `requirements.txt`)

### 安裝與執行
```bash
# 1. 進入專案目錄
cd v2/

# 2. 安裝相依套件
pip install -r requirements.txt

# 3. 測試 CLI 幫助說明
python main.py --help

# 4. 核心功能操作範例
python main.py add --front "Python 的 OCP 是什麼？" --back "開放封閉原則" --deck "CS"
python main.py review --deck "CS"
python main.py stats
```
*(註：因 v1.0 已預先規劃了資料欄位，若您有 v1.0 建立的 `~/.fc/cards.json` 檔案，可直接執行 v2.0，無須任何資料遷移腳本。)*

---

## 7. 已知限制與未來改進方向 (邁向 v3.0)

雖然 v2.0 已經具備高度實用性，但在未來的大規模使用場景下，仍有以下架構升級空間：

1.  **儲存層效能瓶頸 (遷移至 SQLite)：**
    * **現狀：** 目前 `CardRepository` 每次操作都會將整個 JSON 檔案載入記憶體並全覆寫。當卡片數量突破萬張時，將產生明顯的 I/O 延遲。
    * **v3.0 計劃：** 拜 Repository Pattern 所賜，我們只需在 `storage.py` 中新增一個 `SQLiteCardRepository` 類別實作相同介面，並透過依賴注入（Dependency Injection）切換，即可在不改動任何 CLI 邏輯的情況下完成資料庫升級。
2.  **使用者介面升級 (導入 TUI)：**
    * **現狀：** 純文字流的輸出在顯示大量統計數據或長篇背誦內容時不夠直覺。
    * **v3.0 計劃：** 可引入 `Textual` 或 `Rich` 函式庫，將 CLI 升級為 TUI（Terminal User Interface），提供分割視窗、互動式進度條與熱鍵綁定，進一步提升沉浸式學習體驗。
3.  **雲端同步機制：**
    * 目前資料僅存於本地，缺乏跨設備學習能力。未來可考慮在 Repository 層實作 Git-based 同步或簡單的 RESTful API 同步機制。

# storage.py
"""
CardRepository：封裝所有 JSON I/O 邏輯（Repository Pattern）。
對上層（main.py）提供純粹的 domain-level CRUD 介面。
儲存路徑：./data/cards.json（可透過建構參數覆寫）。

v2.0 變動：新增 update(card: Card) -> bool 方法，供 fc edit 與 SM-2
           複習後即時持久化使用；其餘邏輯完全不變。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from models import Card

# 預設資料儲存路徑
DEFAULT_DATA_PATH = Path.home() / ".fc" / "cards.json"


class CardRepository:
    """
    負責 Card 物件與 JSON 檔案之間的讀寫抽象。

    設計要點：
        - 初始化時自動建立目錄與檔案（若不存在）。
        - 所有寫入操作採「先寫暫存檔，再原子性重命名」確保資料完整性。
        - 錯誤發生時輸出至 stderr，並以對應的 Exit Code 結束程式。
    """

    def __init__(self, path: Path = DEFAULT_DATA_PATH) -> None:
        self.path: Path = path
        self._tmp_path: Path = path.with_name(path.name + ".tmp")
        self._ensure_initialized()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """確保資料目錄與 cards.json 存在；若不存在則建立。"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self._exit_permission_denied()

        if not self.path.exists():
            try:
                self._write_raw({"cards": []})
            except PermissionError:
                self._exit_permission_denied()

    # ------------------------------------------------------------------
    # 底層 I/O
    # ------------------------------------------------------------------

    def _read_raw(self) -> dict:
        """讀取並解析 JSON 檔案；解析失敗時報 E03 並結束程式。"""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(
                f"Error: Data file is corrupted. Please inspect {self.path}.",
                file=sys.stderr,
            )
            sys.exit(1)
        except PermissionError:
            self._exit_permission_denied()

    def _write_raw(self, data: dict) -> None:
        """
        原子性寫入：先寫入 .tmp 暫存檔，成功後重命名為正式檔案。
        防止 Ctrl+C 中途中斷導致的資料損毀。
        """
        try:
            with open(self._tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(self._tmp_path, self.path)
        except PermissionError:
            self._exit_permission_denied()

    def _exit_permission_denied(self) -> None:
        """輸出 E05 錯誤訊息並以 Exit Code 1 結束程式。"""
        print(
            f"Error: Permission denied when writing to {self.path}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # 序列化 / 反序列化
    # ------------------------------------------------------------------

    @staticmethod
    def _dict_to_card(item: dict) -> Card:
        """將 JSON dict 轉換為 Card 物件。"""
        return Card(
            id=item["id"],
            front=item["front"],
            back=item["back"],
            deck=item.get("deck", "default"),
            created_at=item.get("created_at", ""),
            next_review_date=item.get("next_review_date"),
            repetitions=item.get("repetitions", 0),
            ease_factor=item.get("ease_factor", 2.5),
            interval=item.get("interval", 0),
        )

    @staticmethod
    def _card_to_dict(card: Card) -> dict:
        """將 Card 物件轉換為可序列化的 JSON dict。"""
        return {
            "id": card.id,
            "front": card.front,
            "back": card.back,
            "deck": card.deck,
            "created_at": card.created_at,
            "next_review_date": card.next_review_date,
            "repetitions": card.repetitions,
            "ease_factor": card.ease_factor,
            "interval": card.interval,
        }

    # ------------------------------------------------------------------
    # 公開 CRUD 介面
    # ------------------------------------------------------------------

    def load(self) -> List[Card]:
        """載入所有字卡並回傳 Card 物件清單。"""
        data = self._read_raw()
        return [self._dict_to_card(item) for item in data.get("cards", [])]

    def save(self, cards: List[Card]) -> None:
        """將 Card 物件清單序列化並寫回檔案。"""
        data = {"cards": [self._card_to_dict(c) for c in cards]}
        self._write_raw(data)

    def find_by_id(self, card_id: str) -> Optional[Card]:
        """依 ID 查詢字卡；找不到時回傳 None。"""
        for card in self.load():
            if card.id == card_id:
                return card
        return None

    def add(self, card: Card) -> None:
        """新增一張字卡至儲存層。"""
        cards = self.load()
        cards.append(card)
        self.save(cards)

    def delete(self, card_id: str) -> bool:
        """
        依 ID 刪除字卡。
        回傳 True 表示刪除成功，False 表示 ID 不存在。
        """
        cards = self.load()
        filtered = [c for c in cards if c.id != card_id]
        if len(filtered) == len(cards):
            return False  # ID 不存在
        self.save(filtered)
        return True

    def update(self, card: Card) -> bool:
        """
        依 ID 更新既有字卡（整張卡片替換，包含 SM-2 欄位）。

        Args:
            card: 已修改完畢的 Card 物件，其 id 必須與儲存層中某張卡片一致。

        Returns:
            True  → 找到對應 ID 並成功更新。
            False → 指定 ID 不存在，檔案未被修改。
        """
        cards = self.load()
        for i, c in enumerate(cards):
            if c.id == card.id:
                cards[i] = card
                self.save(cards)
                return True
        return False
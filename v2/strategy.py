# strategy.py
"""
ReviewStrategy：複習演算法抽象介面與實作（Strategy Pattern）。

v1.0 實作：RandomReviewStrategy（隨機抽卡）。
v2.0 新增：SM2ReviewStrategy（間隔重複演算法）。

v2.0.1 重構：將 update_card 提升至抽象介面，消除 main.py 的 if-else 判斷，
             讓架構回歸純粹的多型呼叫，符合 OCP 與 LSP。
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from models import Card

# SM-2 評分映射：使用者輸入（1–5）→ SM-2 品質參數 q（0–5）
_SCORE_TO_Q: dict[int, int] = {
    1: 0,  # 完全忘記，重置排程
    2: 1,  # 很難想起，重置排程
    3: 2,  # 勉強想起，重置排程（q < 3 視為未通過）
    4: 3,  # 稍有遲疑，通過，間隔正常遞增
    5: 5,  # 完美記住，通過，間隔大幅遞增
}

# SM-2 ease_factor 下限
_MIN_EASE_FACTOR: float = 1.3


class ReviewStrategy(ABC):
    """複習演算法的抽象基底類別。"""

    @abstractmethod
    def select_cards(
        self,
        cards: List[Card],
        limit: Optional[int],
    ) -> List[Card]:
        """
        從候選字卡清單中選出本次複習的字卡。

        Args:
            cards: 所有符合篩選條件的候選字卡。
            limit: 最多複習幾張；None 表示不限制，0 表示不複習任何一張。

        Returns:
            本次實際要複習的字卡清單（已排序 / 已篩選）。
        """
        ...

    @abstractmethod
    def update_card(self, card: Card, score: int) -> Card:
        """
        依使用者評分更新卡片狀態後回傳。

        此方法是「複習後處理」的統一介面。各策略自行決定是否修改卡片欄位：
        - SM2ReviewStrategy：執行 SM-2 公式，更新 repetitions / ease_factor /
          interval / next_review_date。
        - RandomReviewStrategy：No-op，原卡回傳，不修改任何 SM-2 欄位。

        Context（main.py）只需統一呼叫此方法，無需判斷當前策略型別，
        符合開放封閉原則（OCP）與介面隔離原則（ISP）。

        Args:
            card:  本次複習的字卡物件。
            score: 使用者輸入的評分（1–5）。

        Returns:
            處理後的 Card 物件（SM-2 模式為更新後的新狀態；隨機模式為原物件）。
        """
        ...


class RandomReviewStrategy(ReviewStrategy):
    """
    v1.0 預設演算法：隨機打亂候選字卡後，依 limit 截取。

    行為定義：
        - limit=None → 回傳全部（隨機順序）。
        - limit=0    → 回傳空清單。
        - limit>len  → 回傳全部（不足張數不報錯）。

    update_card 為 No-op：隨機模式不更新任何 SM-2 欄位，直接回傳原卡。
    """

    def select_cards(
        self,
        cards: List[Card],
        limit: Optional[int],
    ) -> List[Card]:
        """隨機排序後依 limit 截取。"""
        shuffled = list(cards)
        random.shuffle(shuffled)

        if limit is None:
            return shuffled

        return shuffled[:max(0, limit)]

    def update_card(self, card: Card, score: int) -> Card:
        """
        No-op 實作：隨機模式不修改 SM-2 欄位。

        Args:
            card:  本次複習的字卡（不修改）。
            score: 使用者評分（忽略）。

        Returns:
            原 card 物件，所有欄位保持不變。
        """
        return card


class SM2ReviewStrategy(ReviewStrategy):
    """
    v2.0 預設演算法：基於 SM-2 間隔重複演算法的智慧選卡策略。

    select_cards 邏輯：
        1. 篩選「今日到期」（next_review_date ≤ 本地今日）或「從未複習」
           （next_review_date 為 None）的卡片。
        2. 依 next_review_date 升冪排序（None 排最前，視為最急迫）。
        3. 依 limit 截取。

    update_card 邏輯：
        - 評分 1/2/3（q < 3）：重置 repetitions=0、interval=1，明日複習。
        - 評分 4/5（q >= 3）：依 repetitions 計算新 interval，更新 ease_factor。

    時區處理：
        - next_review_date 寫入 JSON 時使用 UTC ISO 8601 格式。
        - 判斷是否到期時，先將 UTC 字串轉換為本地日期再與本地今日比較。
    """

    # ------------------------------------------------------------------
    # 選卡
    # ------------------------------------------------------------------

    def select_cards(
        self,
        cards: List[Card],
        limit: Optional[int],
    ) -> List[Card]:
        """
        優先選取今日到期或從未複習的卡片，依到期日升冪排序後截取 limit 張。
        """
        local_today: date = date.today()

        due: List[Card] = [
            c for c in cards if self._is_due(c, local_today)
        ]

        due.sort(key=lambda c: (
            c.next_review_date is not None,
            c.next_review_date or "",
        ))

        if limit is None:
            return due

        return due[:max(0, limit)]

    # ------------------------------------------------------------------
    # SM-2 更新
    # ------------------------------------------------------------------

    def update_card(self, card: Card, score: int) -> Card:
        """
        依使用者評分（1–5）執行 SM-2 公式，更新卡片欄位並回傳。

        評分映射：
            1 → q=0, 2 → q=1, 3 → q=2（q < 3，重置）
            4 → q=3, 5 → q=5（q >= 3，通過）

        SM-2 公式：
            若 q < 3：
                repetitions = 0
                interval    = 1
                next_review_date = 今日 + 1 天（UTC）

            若 q >= 3：
                if repetitions == 0: interval = 1
                elif repetitions == 1: interval = 6
                else: interval = round(interval × ease_factor)
                ease_factor = max(1.3, ef + 0.1 - (5-q)×(0.08 + (5-q)×0.02))
                repetitions += 1
                next_review_date = 今日 + interval 天（UTC）

        Args:
            card:  待更新的 Card 物件（原地修改欄位後回傳）。
            score: 使用者輸入的評分（1–5）。

        Returns:
            已更新 SM-2 欄位的 Card 物件。
        """
        q: int = _SCORE_TO_Q[score]
        today_utc: date = datetime.now(timezone.utc).date()

        if q < 3:
            card.repetitions = 0
            card.interval = 1
            card.next_review_date = self._date_to_iso(today_utc + timedelta(days=1))
        else:
            if card.repetitions == 0:
                new_interval: int = 1
            elif card.repetitions == 1:
                new_interval = 6
            else:
                new_interval = round(card.interval * card.ease_factor)

            card.ease_factor = max(
                _MIN_EASE_FACTOR,
                card.ease_factor + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02),
            )
            card.interval = new_interval
            card.repetitions += 1
            card.next_review_date = self._date_to_iso(
                today_utc + timedelta(days=new_interval)
            )

        return card

    # ------------------------------------------------------------------
    # 私有輔助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _is_due(card: Card, local_today: date) -> bool:
        """
        判斷卡片是否今日到期。

        - next_review_date 為 None → 從未複習，視為到期。
        - UTC 字串轉本地日期 ≤ 本地今日 → 到期。
        """
        if card.next_review_date is None:
            return True

        try:
            dt_utc: datetime = datetime.fromisoformat(
                card.next_review_date.replace("Z", "+00:00")
            )
            return dt_utc.astimezone(tz=None).date() <= local_today
        except (ValueError, TypeError):
            return True

    @staticmethod
    def _date_to_iso(d: date) -> str:
        """將 date 物件轉換為 ISO 8601 UTC 格式字串（午夜 UTC）。"""
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
# strategy.py
"""
ReviewStrategy：複習演算法抽象介面與實作（Strategy Pattern）。

v1.0 實作：RandomReviewStrategy（隨機抽卡）。
v2.0 預計：SM2ReviewStrategy（間隔重複演算法）。

升級路徑：新增 SM2ReviewStrategy 並注入 main.py 的 review 指令，
不需修改任何現有邏輯，符合開放封閉原則（OCP）。
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import List, Optional

from models import Card


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


class RandomReviewStrategy(ReviewStrategy):
    """
    v1.0 預設演算法：隨機打亂候選字卡後，依 limit 截取。

    行為定義：
        - limit=None → 回傳全部（隨機順序）。
        - limit=0    → 回傳空清單。
        - limit>len  → 回傳全部（不足張數不報錯）。
    """

    def select_cards(
        self,
        cards: List[Card],
        limit: Optional[int],
    ) -> List[Card]:
        shuffled = list(cards)
        random.shuffle(shuffled)

        if limit is None:
            return shuffled

        # limit 為非負整數（含 0）
        return shuffled[:max(0, limit)]
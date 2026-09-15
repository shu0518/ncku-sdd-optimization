# models.py
"""
Card 資料模型定義。
包含 v1.0 所有欄位，以及 v2.0 SM-2 演算法所需的預留欄位。

v2.0 變動：結構完全不變（models.py 零修改）；
          SM-2 欄位已在 v1.0 預先保留，v2.0 正式啟用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


def _now_iso() -> str:
    """回傳目前 UTC 時間，格式：YYYY-MM-DDTHH:MM:SSZ"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    """回傳新的 UUID v4 字串（小寫，含連字號）。"""
    return str(uuid4())


@dataclass
class Card:
    """
    字卡資料模型。

    必填欄位（建構時需提供）：
        front: 字卡正面內容。
        back:  字卡背面內容。

    選填欄位（有預設值）：
        deck:             所屬牌組，預設為 "default"。
        id:               UUID v4，自動生成。
        created_at:       建立時間戳（ISO 8601 UTC），自動生成。

    SM-2 欄位（v1.0 預先保留，v2.0 正式啟用）：
        next_review_date: 下次複習日期（ISO 8601 UTC 字串），None 表示從未複習。
        repetitions:      連續通過次數（q >= 3）；失敗時重置為 0。
        ease_factor:      簡單度因子，SM-2 預設 2.5，下限 1.3。
        interval:         距下次複習的間隔天數。
    """

    front: str
    back: str
    deck: str = "default"

    # 自動生成欄位
    id: str = field(default_factory=_new_uuid)
    created_at: str = field(default_factory=_now_iso)

    # SM-2 欄位
    next_review_date: Optional[str] = None
    repetitions: int = 0
    ease_factor: float = 2.5
    interval: int = 0
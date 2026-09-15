# main.py
"""
fc CLI 進入點：使用 click 實作所有子指令，整合 storage 與 strategy 模組。

子指令（v1.0，介面凍結）：
    add     新增字卡
    list    列出字卡
    review  互動式複習
    delete  刪除字卡

子指令（v2.0 新增）：
    edit    修改既有字卡（不重置 SM-2 欄位）
    stats   顯示全域學習統計

v2.0.1 重構：
    cmd_review 移除 `if mode == "sm2"` 判斷，
    統一透過 active_strategy.update_card() 多型呼叫，符合 OCP。
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

import click

from models import Card
from storage import CardRepository
from strategy import RandomReviewStrategy, ReviewStrategy, SM2ReviewStrategy

# ──────────────────────────────────────────────
# 常數
# ──────────────────────────────────────────────

SEPARATOR: str = "━━━━━━━━━━━━━━━━━━━━━━━━━━"

_BAR_FULL: str = "█"
_BAR_EMPTY: str = "░"
_BAR_WIDTH: int = 10

_SCORE_LABELS: Dict[int, str] = {
    1: "Forgot",
    2: "Hard",
    3: "Okay",
    4: "Good",
    5: "Perfect",
}

# ──────────────────────────────────────────────
# 模組層級單例（可在測試時替換）
# ──────────────────────────────────────────────

repo: CardRepository = CardRepository()
_sm2_strategy: SM2ReviewStrategy = SM2ReviewStrategy()
_random_strategy: RandomReviewStrategy = RandomReviewStrategy()

# ──────────────────────────────────────────────
# 內部輔助函式
# ──────────────────────────────────────────────

def _build_bar(count: int, max_count: int) -> str:
    """生成固定寬度（_BAR_WIDTH）的 ASCII 長條圖字串。"""
    if max_count == 0:
        filled = 0
    else:
        filled = round((count / max_count) * _BAR_WIDTH)
    filled = max(0, min(_BAR_WIDTH, filled))
    return _BAR_FULL * filled + _BAR_EMPTY * (_BAR_WIDTH - filled)


def _print_review_summary(scores: List[int]) -> None:
    """輸出評分分佈與平均分摘要（呼叫方保證 scores 非空）。"""
    counts: Dict[int, int] = {s: scores.count(s) for s in range(1, 6)}
    max_count: int = max(counts.values())

    click.echo("")
    click.echo("Score Distribution:")
    for s in range(1, 6):
        label = f"{s} ({_SCORE_LABELS[s]})"
        bar = _build_bar(counts[s], max_count)
        click.echo(f"  {label:<12}: {bar}  {counts[s]}")

    avg = sum(scores) / len(scores)
    click.echo(f"Average Score : {avg:.1f}")


def _is_due_today(card: Card, local_today: date) -> bool:
    """判斷卡片是否在本地今日到期（next_review_date ≤ 今日 或為 None）。"""
    if card.next_review_date is None:
        return True
    try:
        dt_utc = datetime.fromisoformat(
            card.next_review_date.replace("Z", "+00:00")
        )
        return dt_utc.astimezone(tz=None).date() <= local_today
    except (ValueError, TypeError):
        return True


# ──────────────────────────────────────────────
# CLI 根指令
# ──────────────────────────────────────────────

@click.group()
def cli() -> None:
    """fc — Flashcard CLI Tool"""


# ──────────────────────────────────────────────
# fc add（v1.0 介面凍結）
# ──────────────────────────────────────────────

@cli.command("add")
@click.option("--front", required=True, help="字卡正面（問題 / 提示）。")
@click.option("--back", required=True, help="字卡背面（答案 / 解釋）。")
@click.option("--deck", default="default", show_default=True, help="所屬牌組名稱。")
def cmd_add(front: str, back: str, deck: str) -> None:
    """新增一張字卡至指定牌組。"""
    card = Card(front=front, back=back, deck=deck)
    repo.add(card)
    click.echo(f"✓ Card added (id: {card.id})")


# ──────────────────────────────────────────────
# fc list（v1.0 介面凍結）
# ──────────────────────────────────────────────

@cli.command("list")
@click.option("--deck", default=None, help="依牌組篩選（不指定則列出所有牌組）。")
def cmd_list(deck: Optional[str]) -> None:
    """列出所有字卡，可依牌組篩選。"""
    cards = repo.load()

    if deck is not None:
        cards = [c for c in cards if c.deck == deck]

    if not cards:
        click.echo("No cards found.")
        return

    id_w = max(len("ID"), max(len(c.id) for c in cards))
    front_w = max(len("Front"), max(len(c.front) for c in cards))
    back_w = max(len("Back"), max(len(c.back) for c in cards))
    ca_w = max(len("Created At"), max(len(c.created_at) for c in cards))

    header = (
        f"{'ID':<{id_w}}  "
        f"{'Front':<{front_w}}  "
        f"{'Back':<{back_w}}  "
        f"{'Created At':<{ca_w}}"
    )
    divider = "-" * len(header)

    click.echo(header)
    click.echo(divider)
    for c in cards:
        click.echo(
            f"{c.id:<{id_w}}  "
            f"{c.front:<{front_w}}  "
            f"{c.back:<{back_w}}  "
            f"{c.created_at:<{ca_w}}"
        )


# ──────────────────────────────────────────────
# fc review（v1.0 介面相容，v2.0 新增 --mode 與統計摘要）
# ──────────────────────────────────────────────

@cli.command("review")
@click.option("--deck", default=None, help="僅複習指定牌組（不指定則複習所有牌組）。")
@click.option("--limit", default=None, type=int, help="本次最多複習幾張（不指定則不限）。")
@click.option(
    "--mode",
    default="sm2",
    show_default=True,
    type=click.Choice(["sm2", "random"], case_sensitive=False),
    help="複習演算法：sm2（預設，智慧排程）或 random（v1.0 隨機模式）。",
)
def cmd_review(deck: Optional[str], limit: Optional[int], mode: str) -> None:
    """開始互動式複習循環。預設採 SM-2 間隔重複演算法選卡。"""
    cards = repo.load()

    if deck is not None:
        cards = [c for c in cards if c.deck == deck]

    # 依模式選擇策略；此後 main.py 只認識 ReviewStrategy 介面
    active_strategy: ReviewStrategy = (
        _sm2_strategy if mode == "sm2" else _random_strategy
    )

    selected = active_strategy.select_cards(cards, limit)
    total = len(selected)

    if total == 0:
        click.echo("Session complete. Reviewed: 0 cards.")
        return

    reviewed: int = 0
    session_scores: List[int] = []

    try:
        for i, card in enumerate(selected, start=1):
            click.echo(f"[Card {i} / {total}]")
            click.echo(SEPARATOR)
            click.echo(f"FRONT: {card.front}")
            click.echo(SEPARATOR)
            click.echo("Press [Enter] to reveal answer...")

            input()

            click.echo(f"\nBACK: {card.back}")
            click.echo(SEPARATOR)

            while True:
                raw = input("Rate your recall (1=Forgot → 5=Perfect): ")
                try:
                    score = int(raw)
                    if 1 <= score <= 5:
                        reviewed += 1
                        session_scores.append(score)

                        # ✅ 純多型呼叫：不再判斷 mode，策略自己決定要不要更新
                        #    SM2ReviewStrategy.update_card → 執行 SM-2 公式
                        #    RandomReviewStrategy.update_card → No-op，原卡回傳
                        updated_card = active_strategy.update_card(card, score)
                        repo.update(updated_card)

                        break
                    else:
                        raise ValueError
                except ValueError:
                    click.echo(
                        "Invalid input. Please enter a number between 1 and 5."
                    )

    except KeyboardInterrupt:
        click.echo("\nReview interrupted.")
        sys.exit(0)

    click.echo(f"Session complete. Reviewed: {reviewed} cards.")

    if reviewed > 0:
        _print_review_summary(session_scores)


# ──────────────────────────────────────────────
# fc delete（v1.0 介面凍結）
# ──────────────────────────────────────────────

@cli.command("delete")
@click.option("--id", "card_id", required=True, help="要刪除的字卡 ID（UUID）。")
@click.option("--yes", is_flag=True, default=False, help="跳過確認提示，直接刪除。")
def cmd_delete(card_id: str, yes: bool) -> None:
    """依 ID 刪除指定字卡。"""
    if not yes:
        try:
            confirm = input(f"Delete card {card_id}? [y/N]: ")
        except KeyboardInterrupt:
            click.echo("")
            return
        if confirm.strip().lower() != "y":
            return

    success = repo.delete(card_id)

    if not success:
        click.echo(f"Error: Card with id '{card_id}' not found.", err=True)
        sys.exit(1)

    click.echo(f"✓ Card {card_id} deleted.")


# ──────────────────────────────────────────────
# fc edit（v2.0 新增）
# ──────────────────────────────────────────────

@cli.command("edit")
@click.option("--id", "card_id", required=True, help="要修改的字卡 ID（UUID）。")
@click.option("--front", default=None, help="新的正面文字。")
@click.option("--back", default=None, help="新的背面文字。")
@click.option("--deck", default=None, help="新的牌組名稱。")
def cmd_edit(
    card_id: str,
    front: Optional[str],
    back: Optional[str],
    deck: Optional[str],
) -> None:
    """修改既有字卡的正面、背面或牌組，不重置 SM-2 欄位。"""
    if front is None and back is None and deck is None:
        click.echo(
            "Error: At least one of --front, --back, --deck must be provided.",
            err=True,
        )
        sys.exit(2)

    card = repo.find_by_id(card_id)

    if card is None:
        click.echo(f"Error: Card with id '{card_id}' not found.", err=True)
        sys.exit(1)

    if front is not None:
        card.front = front
    if back is not None:
        card.back = back
    if deck is not None:
        card.deck = deck

    repo.update(card)
    click.echo(f"✓ Card {card_id} updated.")


# ──────────────────────────────────────────────
# fc stats（v2.0 新增）
# ──────────────────────────────────────────────

@cli.command("stats")
@click.option("--deck", default=None, help="僅顯示指定牌組的統計（不指定則顯示所有）。")
def cmd_stats(deck: Optional[str]) -> None:
    """顯示各牌組的全域學習統計（唯讀，不修改任何資料）。"""
    all_cards = repo.load()

    if deck is not None:
        all_cards = [c for c in all_cards if c.deck == deck]

    if not all_cards:
        click.echo("No stats available.")
        return

    local_today: date = date.today()

    deck_stats: Dict[str, Dict] = defaultdict(
        lambda: {"cards": 0, "due": 0, "ease_sum": 0.0}
    )

    for card in all_cards:
        ds = deck_stats[card.deck]
        ds["cards"] += 1
        ds["ease_sum"] += card.ease_factor
        if _is_due_today(card, local_today):
            ds["due"] += 1

    sorted_decks = sorted(deck_stats.keys())

    deck_col_w: int = max(len("Deck"), max(len(d) for d in sorted_decks))
    cards_col_w: int = len("Cards")
    due_col_w: int = len("Due Today")
    ease_col_w: int = len("Avg Ease")

    total_cards: int = sum(ds["cards"] for ds in deck_stats.values())
    total_due: int = sum(ds["due"] for ds in deck_stats.values())
    total_ease_avg: float = (
        sum(ds["ease_sum"] for ds in deck_stats.values()) / total_cards
    )

    header = (
        f"{'Deck':<{deck_col_w}}  "
        f"{'Cards':>{cards_col_w}}  "
        f"{'Due Today':>{due_col_w}}  "
        f"{'Avg Ease':>{ease_col_w}}"
    )
    divider = (
        f"{'─' * deck_col_w}  "
        f"{'─' * cards_col_w}  "
        f"{'─' * due_col_w}  "
        f"{'─' * ease_col_w}"
    )

    click.echo(header)
    click.echo(divider)

    for dn in sorted_decks:
        ds = deck_stats[dn]
        avg_ease: float = ds["ease_sum"] / ds["cards"]
        click.echo(
            f"{dn:<{deck_col_w}}  "
            f"{ds['cards']:>{cards_col_w}}  "
            f"{ds['due']:>{due_col_w}}  "
            f"{avg_ease:>{ease_col_w}.2f}"
        )

    click.echo(divider)
    click.echo(
        f"{'Total':<{deck_col_w}}  "
        f"{total_cards:>{cards_col_w}}  "
        f"{total_due:>{due_col_w}}  "
        f"{total_ease_avg:>{ease_col_w}.2f}"
    )


# ──────────────────────────────────────────────
# 進入點
# ──────────────────────────────────────────────

if __name__ == "__main__":
    cli()
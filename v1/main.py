# main.py
"""
fc CLI 進入點：使用 click 實作所有子指令，整合 storage 與 strategy 模組。

子指令：
    add     新增字卡
    list    列出字卡
    review  互動式複習
    delete  刪除字卡
"""

from __future__ import annotations

import sys
from typing import Optional
 
import click

from models import Card
from storage import CardRepository
from strategy import RandomReviewStrategy, ReviewStrategy

# ──────────────────────────────────────────────
# 常數
# ──────────────────────────────────────────────

SEPARATOR: str = "━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ──────────────────────────────────────────────
# 模組層級單例（可在測試時替換）
# ──────────────────────────────────────────────

repo: CardRepository = CardRepository()
strategy: ReviewStrategy = RandomReviewStrategy()


# ──────────────────────────────────────────────
# CLI 根指令
# ──────────────────────────────────────────────

@click.group()
def cli() -> None:
    """fc — Flashcard CLI Tool"""


# ──────────────────────────────────────────────
# fc add
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
# fc list
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

    # 計算各欄位最大寬度以對齊輸出
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
# fc review
# ──────────────────────────────────────────────

@cli.command("review")
@click.option("--deck", default=None, help="僅複習指定牌組（不指定則複習所有牌組）。")
@click.option("--limit", default=None, type=int, help="本次最多複習幾張（不指定則不限）。")
def cmd_review(deck: Optional[str], limit: Optional[int]) -> None:
    """開始互動式複習循環。"""
    cards = repo.load()

    if deck is not None:
        cards = [c for c in cards if c.deck == deck]

    selected = strategy.select_cards(cards, limit)
    total = len(selected)

    # 步驟 2：沒有任何字卡可複習
    if total == 0:
        click.echo("Session complete. Reviewed: 0 cards.")
        return

    reviewed: int = 0

    try:
        for i, card in enumerate(selected, start=1):
            # 步驟 3：顯示正面
            click.echo(f"[Card {i} / {total}]")
            click.echo(SEPARATOR)
            click.echo(f"FRONT: {card.front}")
            click.echo(SEPARATOR)
            click.echo("Press [Enter] to reveal answer...")

            # 步驟 4：等待用戶按 Enter（Ctrl+C 觸發 KeyboardInterrupt）
            input()

            # 步驟 5：顯示背面
            click.echo(f"\nBACK: {card.back}")
            click.echo(SEPARATOR)

            # 步驟 6 / 6a：評分循環
            while True:
                raw = input("Rate your recall (1=Forgot → 5=Perfect): ")
                try:
                    score = int(raw)
                    if 1 <= score <= 5:
                        # 有效評分：v1.0 僅記錄，v2.0 將用於 SM-2
                        reviewed += 1
                        break
                    else:
                        raise ValueError
                except ValueError:
                    # E04：無效輸入，不中斷流程，重新提示
                    click.echo(
                        "Invalid input. Please enter a number between 1 and 5."
                    )

    except KeyboardInterrupt:
        # 步驟 8：Ctrl+C 優雅中斷，Exit Code 0
        click.echo("\nReview interrupted.")
        sys.exit(0)

    # 步驟 7：輸出摘要
    click.echo(f"Session complete. Reviewed: {reviewed} cards.")


# ──────────────────────────────────────────────
# fc delete
# ──────────────────────────────────────────────

@cli.command("delete")
@click.option("--id", "card_id", required=True, help="要刪除的字卡 ID（UUID）。")
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="跳過確認提示，直接刪除。",
)
def cmd_delete(card_id: str, yes: bool) -> None:
    """依 ID 刪除指定字卡。"""
    if not yes:
        # 互動式確認提示（格式完全符合規格書）
        try:
            confirm = input(f"Delete card {card_id}? [y/N]: ")
        except KeyboardInterrupt:
            click.echo("")
            return
        if confirm.strip().lower() != "y":
            return  # 用戶取消，靜默結束

    success = repo.delete(card_id)

    if not success:
        # E01：ID 不存在，輸出至 stderr，Exit Code 1
        click.echo(
            f"Error: Card with id '{card_id}' not found.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"✓ Card {card_id} deleted.")


# ──────────────────────────────────────────────
# 進入點
# ──────────────────────────────────────────────

if __name__ == "__main__":
    cli()
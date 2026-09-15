# fc — Flashcard CLI (SDD: v1 -> v2)

> A terminal flashcard tool built by spec-driven development: v1.0 ships a random-draw CLI with a forward-looking architecture, and v2.0 adds an SM-2 spaced-repetition scheduler on top of it without changing the storage layer or the data schema.

`Course project` · Netdb Lab, NCKU · AIASE 2026 · Individual
**Stack:** Python >= 3.10 · Click · SM-2 spaced-repetition algorithm · JSON (atomic-write repository)

## Overview

`fc` is a keyboard-driven flashcard CLI (`add`, `list`, `review`, `delete` in v1; `edit`, `stats` added in v2). v1.0 (210-line `main.py`, 493 lines total) implements a `RandomReviewStrategy` behind a `ReviewStrategy` abstract base class, and a `CardRepository` that persists cards to JSON with an atomic temp-file-then-rename write. v2.0 (397-line `main.py`, 893 lines total) adds `SM2ReviewStrategy`, which schedules cards by the SM-2 algorithm instead of drawing randomly. Because the `Card` dataclass already carried SM-2 fields (`ease_factor`, `next_review_date`) since v1, and the review algorithm was already behind an interface, v2 required no JSON migration script and no change to `main.py`'s review loop — only a new strategy class and a `--mode` flag to select it.

## Key Design Decisions

| Decision | Rationale |
| --- | --- |
| `ReviewStrategy` abstract base class in v1, with only `RandomReviewStrategy` implemented | v2 could add `SM2ReviewStrategy` and swap it in without touching the interactive review loop in `main.py` |
| `CardRepository` (Repository pattern) with atomic write (temp file + `os.replace`) | Storage backend can change later without touching `main.py`; the atomic rename means a `Ctrl+C` mid-write can't corrupt `cards.json` |
| SM-2 fields (`ease_factor`, `next_review_date`) reserved on the `Card` dataclass since v1, unused until v2 | v2 needed no JSON migration script — old cards with those fields unset are treated by the new algorithm as never-reviewed cards |
| Rating-to-quality mapping skips q=4 (1->q0, 2->q1, 3->q2, 4->q3, 5->q5) | SM-2 splits pass/fail at q>=3; q=3 ("hesitant") and q=5 ("perfect recall") map cleanly to ratings 4 and 5, while q=4 has no rating that isn't already ambiguous with q=3 on a 5-point scale |
| Click instead of `argparse` for the CLI | v2's new `edit` and `stats` subcommands were added via Click's decorator routing without modifying the v1 parser code |

## Challenges

**Problem.** SM-2 scheduling needs day-granularity comparison against "today" to decide which cards are due, but timestamps stored in the user's local time would make that comparison inconsistent if the user reviews cards from a different timezone.
**Approach.** `models.py` persists every timestamp as UTC ISO 8601. `SM2ReviewStrategy.select_cards` converts UTC to the user's local time in memory, and compares that converted date against the local calendar day — the conversion happens only at comparison time, never in storage.
**Result.** Due-date data stays timezone-independent in storage while "is this card due today" still matches the user's local calendar day, regardless of which timezone wrote the original timestamp.

## Limitations

- No automated test suite: `T01`–`T10` in `v1/sdd_v1.md` are manually-run CLI acceptance scenarios (command, precondition, expected stdout, exit code) verified by inspection, not `pytest` cases.
- `CardRepository` loads and rewrites the entire JSON file on every operation; the repo's own v3.0 notes flag this as a likely I/O bottleneck at large card counts, but that threshold has not been benchmarked.
- The q=4 skip in the rating-to-quality mapping is a design choice, not validated against user data — TODO if empirical tuning is wanted.
- No sync between devices; all data is a single local JSON file.

## Running It

```bash
cd v2/
pip install -r requirements.txt

python main.py --help
python main.py add --front "What is the OCP?" --back "Open/Closed Principle" --deck "CS"
python main.py review --deck "CS"          # SM-2 by default; --mode random for v1 behavior
python main.py stats
```

## Structure

    v1/              Proof of concept: RandomReviewStrategy, Repository pattern, JSON storage
    v2/               Adds SM2ReviewStrategy, `edit`/`stats` commands, `--mode` flag
    v1/sdd_v1.md      v1 spec, including the T01-T10 acceptance-test table
    v2/sdd_v2.md      v2 spec (SM-2 requirements, backward-compatibility constraints)

---
Original course-assignment README (in Chinese): [docs/course-requirements.md](docs/course-requirements.md)

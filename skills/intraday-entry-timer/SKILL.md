---
name: intraday-entry-timer
description: Watch a day-trading setup bar by bar on free Yahoo 1-minute or 5-minute bars and say the moment to get in. Builds the opening range (first 15 minutes by default) and calls the entry on the first completed bar that CLOSES above the range high or above a level, with an optional volume check and an entry window. Long side only, never places an order. Use when the user says "tell me when to get in", "watch TSLA", "has it broken out", "did it break the opening range", "time my entry", "check my watchlist", or after intraday-scanner and before intraday-exit-planner.
argument-hint: "[TICKER] [--setup orb|level] [--interval 5m|1m]"
---

# Intraday Entry Timer

## Overview

Turn a setup into one moment: the bar that confirms it. Read bars, 1-minute or 5-minute, and wait for each one to finish. A price that pokes above the high in the middle of a bar is not an entry. A bar that CLOSES above it is. Then say the time and the price, write them down for `intraday-exit-planner`, and stop. It never buys anything. Day trading loses most people money, and a clean signal does not change that.

## When to Use

- The user asks to watch a ticker for a breakout, or "tell me when to get in"
- The user asks whether a stock broke its opening range
- After `intraday-scanner` found hits, to check the whole watchlist
- Before `intraday-exit-planner`, which plans from this skill's report

## Prerequisites

- No API key. Bars come from Yahoo Finance's free chart endpoint (unofficial, can lag)
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for the shared NYSE calendar

## Workflow

### Step 1: Pick the symbol

Get it from the user, or check every hit of the newest scanner report. Check the stock's news first (`market-news-analyst`).

<!-- exec: api -->
```bash
python3 skills/intraday-entry-timer/scripts/intraday_entry.py watchlist
python3 skills/intraday-entry-timer/scripts/intraday_entry.py watchlist --watchlist reports/intraday_scanner_orb_2026-10-19_1015.json
```

### Step 2: Check the setup now

<!-- exec: api -->
```bash
python3 skills/intraday-entry-timer/scripts/intraday_entry.py check TSLA
python3 skills/intraday-entry-timer/scripts/intraday_entry.py check TSLA --setup level --level 371.20
python3 skills/intraday-entry-timer/scripts/intraday_entry.py check TSLA --interval 1m --min-volume-x 1.5
```

Tell the user the status in one line: waiting and how far, triggered at what time and price, expired, or no data.

### Step 3: Wait for it (optional)

Run `watch` in the background, or `check` on a `/loop` every 5 minutes:

<!-- exec: api -->
```bash
python3 skills/intraday-entry-timer/scripts/intraday_entry.py watch TSLA --until 15:30
```

`watch` wakes just after each bar closes, prints one line per closed bar, exits 0 on the trigger (and writes the entry report) or 1 when the setup expires. Keep the computer awake while it watches: a sleeping laptop pauses it and it catches up, late, when it wakes. Never run order execution from a background watch: nobody is there to say yes.

### Step 4: Report the trigger

Say the time and the price, and that nothing was placed. If the trigger is more than a bar old, say that too: a late entry is a different trade (the price, the stop distance and the odds have moved).

### Step 5: Hand off

Hand off to `intraday-exit-planner` to set the stop and the target BEFORE anything is bought.

Flags: `--setup orb|level`, `--or-minutes` (15), `--interval 5m|1m`, `--level PRICE`, `--min-volume-x X`, `--no-entries-before` (09:45), `--no-entries-after` (15:30), `--now "2026-10-19 10:15"` (New York time) to replay a day, `--offline PATH` (saved Yahoo chart JSON, `.json`/`.json.gz`, or a folder of `<TICKER>.json`), `--output-dir` (reports/), `--no-write`, `--json`. Read `references/entry_rules.md` for the full rule.

## Output Format

`check` (and `watch` on a trigger) writes `reports/intraday_entry_<TICKER>_<date>.json` and `.md`:

```json
{"created_by": "intraday-entry-timer", "symbol": "TSLA", "setup": "orb", "side": "buy", "date": "2026-10-19",
 "status": "triggered", "time": "10:15 AM", "bar_start": "10:10", "bar_index": 8, "price": 364.18,
 "level": 362.18, "interval": "5m", "opening_range": {"high": 362.18, "low": 354.47, "minutes": 15},
 "source": "yahoo", "checked_at": "2026-10-19T14:15:00Z", "reason": null}
```

Status is `triggered`, `waiting`, `expired` or `no-data`. Exit code 0 = triggered, 1 = anything else, 2 = NYSE calendar dependency missing.

## Example: TSLA on Monday 2026-10-19

5-minute bars, opening range 354.47 to 362.18. At 10:12 the 10:10 bar is still open, so it waits:

```text
WAITING  last close $361.68 (10:05 bar), $0.50 under the range high $362.18 (-0.14%).
The 10:10 bar is still forming ($364.18 so far, closes 10:15 AM); it does not count until it closes.
```

At 10:15 the bar has closed:

```text
TRIGGERED 10:15 AM at $364.18: the 10:10 bar (bar 8) closed above the range high $362.18 (+0.55%).
This is the moment to get in, if you take the trade. Nothing was placed.
```

With `--min-volume-x 1` the 10:10 bar is too thin (0.60x the range's volume) and the trigger moves to 10:35 AM at $365.75.

## Resources

- `scripts/intraday_entry.py`: the entry timer CLI (`check`, `watch`, `watchlist`)
- `scripts/_market_calendar.py`: the shared XNYS calendar (generated, do not edit)
- `references/entry_rules.md`: the opening range, the trigger, closed-bar rules, the entry window and statuses

## Key Principles

1. Bar by bar, on free Yahoo bars that are unofficial and can lag. Say so when a minute matters.
2. A signal is information, not an order, and not a promise.
3. Longs only. If the user wants a short, say that this skill does not plan shorts.
4. One trigger per setup per day: the first close above. Later closes do not reset it.
5. Never call an entry early because a bar looks like it will close above.

## Safety

- Education and tooling, not financial advice. Day trading loses most people money.
- Nothing in the intraday skills places an order. An order only follows `position-sizer --intraday-plan`, `pre-trade-discipline-gate`, and an explicit yes from the user for that exact order, sent through `portfolio-manager` (Alpaca MCP, paper account first). Keep broker order tools on "Needs approval", never "Always allow".
- Longs only. No options, margin, short selling or leverage.
- Broker keys live in environment variables, never in the chat.

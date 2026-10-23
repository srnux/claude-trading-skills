---
layout: default
title: "Intraday Entry Timer"
grand_parent: English
parent: Skill Guides
nav_order: 38
lang_peer: /ja/skills/intraday-entry-timer/
permalink: /en/skills/intraday-entry-timer/
generated: true
---

# Intraday Entry Timer
{: .no_toc }

Watch a day-trading setup bar by bar on free Yahoo 1-minute or 5-minute bars and say the moment to get in. Builds the opening range (first 15 minutes by default) and calls the entry on the first completed bar that CLOSES above the range high or above a level, with an optional volume check and an entry window. Long side only, never places an order. Use when the user says "tell me when to get in", "watch TSLA", "has it broken out", "did it break the opening range", "time my entry", "check my watchlist", or after intraday-scanner and before intraday-exit-planner.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/intraday-entry-timer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/intraday-entry-timer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Turn a setup into one moment: the bar that confirms it. Read bars, 1-minute or 5-minute, and wait for each one to finish. A price that pokes above the high in the middle of a bar is not an entry. A bar that CLOSES above it is. Then say the time and the price, write them down for `intraday-exit-planner`, and stop. It never buys anything. Day trading loses most people money, and a clean signal does not change that.

---

## 2. When to Use

- The user asks to watch a ticker for a breakout, or "tell me when to get in"
- The user asks whether a stock broke its opening range
- After `intraday-scanner` found hits, to check the whole watchlist
- Before `intraday-exit-planner`, which plans from this skill's report

---

## 3. Prerequisites

- No API key. Bars come from Yahoo Finance's free chart endpoint (unofficial, can lag)
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for the shared NYSE calendar

---

## 4. Quick Start

```bash
python3 skills/intraday-entry-timer/scripts/intraday_entry.py watchlist
python3 skills/intraday-entry-timer/scripts/intraday_entry.py watchlist --watchlist reports/intraday_scanner_orb_2026-10-19_1015.json
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/intraday-entry-timer/references/entry_rules.md`

**Scripts:**

- `skills/intraday-entry-timer/scripts/_market_calendar.py`
- `skills/intraday-entry-timer/scripts/intraday_entry.py`

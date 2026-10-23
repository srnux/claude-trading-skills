---
layout: default
title: "Intraday Scanner"
grand_parent: English
parent: Skill Guides
nav_order: 40
lang_peer: /ja/skills/intraday-scanner/
permalink: /en/skills/intraday-scanner/
generated: true
---

# Intraday Scanner
{: .no_toc }

Scan thousands of US stock charts for day-trading setups using free Yahoo Finance data. Builds the US common-stock universe from Nasdaq Trader's symbol directories, runs a pre-market scan of daily closes (20-day closing-high breakout, bull flag, 20-day average reclaim, oversold, oversold bounce) and an intraday opening-range breakout scan on 5-minute bars. Use when the user asks to scan the market for day trades, find opening-range breakouts, build an intraday watchlist, run a pre-market scan, or asks what is breaking out this morning.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/intraday-scanner.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/intraday-scanner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

First step of the intraday workflow. Read thousands of free charts and list the ones that match a rule. A scan is a list of charts that match a rule, not a list of stocks to buy, and a setup on a chart is not a prediction. Day trading loses most people money. The scanner only saves flipping through 5,000 charts by hand.

Two scans:

- **daily** (before the open): setups from daily closes, for the watchlist of the day
- **orb** (after 9:50 AM ET): opening-range breakouts so far today, from 5-minute bars

---

## 2. When to Use

- The user asks to "scan the market", "find me setups", "what is breaking out", "opening range breakouts"
- The user wants a pre-market watchlist or asks "what should I look at today"
- At the start of a day-trading session, before `intraday-entry-timer`

---

## 3. Prerequisites

- No API key. Data comes from Yahoo Finance's free chart and spark endpoints (unofficial, can lag) and Nasdaq Trader's public symbol files
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for the shared NYSE calendar (holidays, 1:00 p.m. early closes)

---

## 4. Quick Start

```bash
python3 skills/intraday-scanner/scripts/intraday_scanner.py universe
```

---

## 5. Workflow

### Step 1: Build the universe (about once a week)

<!-- exec: api -->
```bash
python3 skills/intraday-scanner/scripts/intraday_scanner.py universe
```

Writes `state/intraday/universe.txt`, one `SYMBOL|Name` a line. Read `references/scan_rules.md` for the inclusion rule (common stock, ordinary shares and ADRs, no ETFs, warrants, units or preferreds).

### Step 2: Pre-market scan (before 9:30 AM ET)

<!-- exec: api -->
```bash
python3 skills/intraday-scanner/scripts/intraday_scanner.py daily --output-dir reports/
python3 skills/intraday-scanner/scripts/intraday_scanner.py daily --symbols TSLA,NVDA,AMD --output-dir reports/
```

Report the counts to the user (fetched, liquid, scanned, hits) and the top few hits by setup.

### Step 3: Opening-range breakout scan (after 9:50 AM ET, 10:15 is the classic)

<!-- exec: api -->
```bash
python3 skills/intraday-scanner/scripts/intraday_scanner.py orb --output-dir reports/
python3 skills/intraday-scanner/scripts/intraday_scanner.py orb --at 10:15 --watchlist reports/intraday_scanner_daily_2026-10-19.json
```

Say how many usable charts broke their range and when. A later hit is closer to the current price. When stage 2 stops short it prints PARTIAL with the count it skipped: say so, never round a partial scan up to "the whole market".

### Step 4: Hand off

The user picks one chart. Never pick for them. Check its news first (`market-news-analyst`), then time the entry with `intraday-entry-timer`.

Useful flags: `--min-price` (default 5), `--min-volume` (daily 1,000,000, orb 0), `--or-minutes` (15), `--max-confirm` (200, 0 = all), `--until` (15:30, no new entries after), `--now "2026-10-19 10:15"` to pin the New York clock, `--offline PATH` to replay saved Yahoo files, `--no-write`, `--json`. Exit code 0 when the scan found something, 1 when it found nothing or could not run, 2 when the NYSE calendar dependency is missing.

---

## 6. Resources

**References:**

- `skills/intraday-scanner/references/scan_rules.md`

**Scripts:**

- `skills/intraday-scanner/scripts/_market_calendar.py`
- `skills/intraday-scanner/scripts/intraday_scanner.py`

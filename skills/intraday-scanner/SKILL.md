---
name: intraday-scanner
description: Scan thousands of US stock charts for day-trading setups using free Yahoo Finance data. Builds the US common-stock universe from Nasdaq Trader's symbol directories, runs a pre-market scan of daily closes (20-day closing-high breakout, bull flag, 20-day average reclaim, oversold, oversold bounce) and an intraday opening-range breakout scan on 5-minute bars. Use when the user asks to scan the market for day trades, find opening-range breakouts, build an intraday watchlist, run a pre-market scan, or asks what is breaking out this morning.
argument-hint: "[universe | daily | orb] [--at HH:MM]"
---

# Intraday Scanner

## Overview

First step of the intraday workflow. Read thousands of free charts and list the ones that match a rule. A scan is a list of charts that match a rule, not a list of stocks to buy, and a setup on a chart is not a prediction. Day trading loses most people money. The scanner only saves flipping through 5,000 charts by hand.

Two scans:

- **daily** (before the open): setups from daily closes, for the watchlist of the day
- **orb** (after 9:50 AM ET): opening-range breakouts so far today, from 5-minute bars

## When to Use

- The user asks to "scan the market", "find me setups", "what is breaking out", "opening range breakouts"
- The user wants a pre-market watchlist or asks "what should I look at today"
- At the start of a day-trading session, before `intraday-entry-timer`

## Prerequisites

- No API key. Data comes from Yahoo Finance's free chart and spark endpoints (unofficial, can lag) and Nasdaq Trader's public symbol files
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for the shared NYSE calendar (holidays, 1:00 p.m. early closes)

## Workflow

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

## Output Format

Each scan writes a JSON + Markdown pair to `reports/`:

- `intraday_scanner_daily_<date>.json` / `.md`
- `intraday_scanner_orb_<date>_<HHMM>.json` / `.md`

```json
{
  "created_by": "intraday-scanner", "mode": "orb", "as_of": "2026-10-19 10:15 ET",
  "universe": 234, "scanned": 231, "failed": 1, "unconfirmed": 0, "source": "yahoo",
  "or_minutes": 15, "interval": "5m", "filters": {"min_price": 0.0, "min_volume": 0},
  "hits": [{"symbol": "TSLA", "setups": ["orb"], "price": 364.18, "at": "10:15 AM", "bar_start": "10:10",
            "bar_index": 8, "or_high": 362.18, "or_low": 354.47, "pct_over": 0.55}]
}
```

`intraday-entry-timer watchlist` reads `hits[].symbol` from the newest report.

## Example: TSLA on Monday 2026-10-19

A 10:15 AM scan over a 234-ticker list of real Yahoo charts found 42 of 231 usable charts closed above their opening-range high. TSLA is one: range 354.47 to 362.18, the 10:10 bar closed at $364.18, 0.55% over the top, at 10:15 AM.

## Resources

- `scripts/intraday_scanner.py`: the scanner CLI (`universe`, `daily`, `orb`)
- `scripts/_market_calendar.py`: the shared XNYS calendar (generated, do not edit)
- `references/scan_rules.md`: universe rule, daily setup definitions, the two-stage ORB scan, bar rules and data limits

## Key Principles

1. Say what was scanned: how many symbols, how many charts came back, how many were usable, and the time of the data.
2. Say "matched a rule", never "a buy", "a winner" or "a good trade".
3. Never print a P&L, a return or a profit figure.
4. A hit is stale once the price has moved on. Re-run before acting on it.
5. Bars are 5-minute bars checked bar by bar, never tick by tick. Free data can lag.

## Safety

- Education and tooling, not financial advice. Day trading loses most people money.
- Nothing in the intraday skills places an order. An order only follows `position-sizer --intraday-plan`, `pre-trade-discipline-gate`, and an explicit yes from the user for that exact order, sent through `portfolio-manager` (Alpaca MCP, paper account first). Keep broker order tools on "Needs approval", never "Always allow".
- Longs only. No options, margin, short selling or leverage.
- Broker keys live in environment variables, never in the chat.

---
name: intraday-alerts
description: Price alerts and the NYSE clock for an open day trade. Turns the intraday-exit-planner plan into three alerts in one go (the stop, the target and "flat by close"), plus above / below / percent-move / time-of-day / opening-bell rules, each ringing once. Knows NYSE hours, holidays and early closes from the shared calendar, works in New York time, and reads free delayed quotes (Yahoo chart JSON, Stooq CSV). Use when the user says "alert me when", "tell me if TSLA hits", "watch my stop", "remind me to close by 3:55", "is the market open", "when does the market open", "get me a price", or right after intraday-exit-planner writes a plan.
argument-hint: "[ticker] [price]"
---

# Intraday Alerts

## Overview

Watch the numbers so the user does not have to stare at a chart. An alert is information, never an order: when a stop alert rings, nothing is sold by this skill. With a bracket order the stop-loss and the take-profit already sit at the broker and do the work. The alerts tell the user what happened and when it is time to be flat.

## When to Use

- Right after `intraday-exit-planner` writes a plan: stop, target and flat-by alerts
- The user asks to be alerted at a price, a percent move or a time of day
- The user asks whether the NYSE is open, or when it opens or closes
- The user wants a delayed quote for one or more tickers

## Prerequisites

- No API key. Quotes come from Yahoo Finance's free chart JSON (default) or Stooq's free CSV, delayed and unofficial
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for the shared NYSE calendar

## Workflow

### Step 1: Arm the plan's alerts

<!-- exec: api -->
```bash
python3 skills/intraday-alerts/scripts/intraday_alerts.py add --from-plan
python3 skills/intraday-alerts/scripts/intraday_alerts.py add --from-plan --plan reports/intraday_exit_plan_TSLA_2026-10-19.json
```

Without `--plan` it reads the newest `reports/intraday_exit_plan_*.json`. Confirm the three alerts back to the user: the stop, the target and the flat-by time, each for the plan's day only.

### Step 2: Add other rules (optional)

<!-- exec: api -->
```bash
python3 skills/intraday-alerts/scripts/intraday_alerts.py add --opening-bell
python3 skills/intraday-alerts/scripts/intraday_alerts.py add --symbol TSLA --stop 358.32
python3 skills/intraday-alerts/scripts/intraday_alerts.py add --symbol KO --pct 3
python3 skills/intraday-alerts/scripts/intraday_alerts.py add --at 15:55 --label "flat by close" --before-close
```

### Step 3: Check while the trade is open

<!-- exec: api -->
```bash
python3 skills/intraday-alerts/scripts/intraday_alerts.py check
```

Run it every few minutes from a scheduled task or `/loop`. Each run fetches only the tickers in today's rules and rings each alert once. A check reads the latest delayed quote: it is not a live feed, and a price can pass a level between two checks. Exit code 0 = something rang, 1 = nothing rang.

### Step 4: Say what rang

Tell the user what rang in one line each. A stop or target alert means the bracket order has probably filled: check the position with `portfolio-manager`. "Flat by close" means close anything still open. The user sends that sell at the broker after `pre-trade-discipline-gate`. Never act for them.

Other commands: `clock` (is the NYSE open, next open), `quote TSLA KO --write` (delayed quotes), `list`, `reset <id>`. Flags: `--source yahoo|stooq`, `--offline DIR`, `--now "2026-10-19 15:55"` (New York time), `--json`. Read `references/alert_rules.md` for rule types, quotes and the clock.

## Output Format

State lives in `state/intraday/` (git-ignored):

| file | what |
| --- | --- |
| `state/intraday/alerts.json` | the rules (`assets/alerts.example.json` is a complete example) |
| `state/intraday/alerts_state.json` | which rules rang and when, so each rings once |
| `state/intraday/prices.json` | the latest quotes with their quote time, merged in. `position-sizer --intraday-plan` can read a fresh price from it |

## Example: TSLA on Monday 2026-10-19

Entry $364.18 at 10:15 AM, stop $358.32, target $370.04, flat by 15:55. `add --from-plan` writes `tsla-plan-stop`, `tsla-plan-target` and `tsla-flat-by` for that day. A `check` at 10:53 reads the real 10:52 quote, $366.48, between the stop and the target:

```text
NYSE OPEN (2026-10-19 10:53 New York, regular session).
Nothing hit. 3 rule(s) watched today, TSLA $366.48.
```

At 3:55 PM it rings once: "Flat by close: it is 15:55 New York (set for 15:55), the market closes at 16:00." The next morning the plan's alerts are no longer watched.

## Resources

- `scripts/intraday_alerts.py`: the alerts CLI (`clock`, `quote`, `add`, `check`, `list`, `reset`)
- `scripts/_market_calendar.py`: the shared XNYS calendar (generated, do not edit)
- `references/alert_rules.md`: rule types, re-arming, early-close shifts, quote sources and the NYSE clock
- `assets/alerts.example.json`: an example rules file

## Key Principles

1. An alert is a fact about a price or the clock. Say it as a fact.
2. Never present a quote as live. Free quotes are delayed and unofficial. The broker's price is the one that fills.
3. Confirm every new rule back to the user: ticker, type, level, day.
4. Never predict where a price is going.

## Safety

- Education and tooling, not financial advice. Day trading loses most people money.
- Nothing in the intraday skills places, cancels or changes an order. An order only follows `position-sizer --intraday-plan`, `pre-trade-discipline-gate`, and an explicit yes from the user for that exact order, sent through `portfolio-manager` (Alpaca MCP, paper account first). Keep broker order tools on "Needs approval", never "Always allow".
- Longs only. No options, margin, short selling or leverage.
- Broker keys live in environment variables, never in the chat.

---
layout: default
title: "Intraday Alerts"
grand_parent: English
parent: Skill Guides
nav_order: 37
lang_peer: /ja/skills/intraday-alerts/
permalink: /en/skills/intraday-alerts/
generated: true
---

# Intraday Alerts
{: .no_toc }

Price alerts and the NYSE clock for an open day trade. Turns the intraday-exit-planner plan into three alerts in one go (the stop, the target and "flat by close"), plus above / below / percent-move / time-of-day / opening-bell rules, each ringing once. Knows NYSE hours, holidays and early closes from the shared calendar, works in New York time, and reads free delayed quotes (Yahoo chart JSON, Stooq CSV). Use when the user says "alert me when", "tell me if TSLA hits", "watch my stop", "remind me to close by 3:55", "is the market open", "when does the market open", "get me a price", or right after intraday-exit-planner writes a plan.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/intraday-alerts.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/intraday-alerts){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Watch the numbers so the user does not have to stare at a chart. An alert is information, never an order: when a stop alert rings, nothing is sold by this skill. With a bracket order the stop-loss and the take-profit already sit at the broker and do the work. The alerts tell the user what happened and when it is time to be flat.

---

## 2. When to Use

- Right after `intraday-exit-planner` writes a plan: stop, target and flat-by alerts
- The user asks to be alerted at a price, a percent move or a time of day
- The user asks whether the NYSE is open, or when it opens or closes
- The user wants a delayed quote for one or more tickers

---

## 3. Prerequisites

- No API key. Quotes come from Yahoo Finance's free chart JSON (default) or Stooq's free CSV, delayed and unofficial
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for the shared NYSE calendar

---

## 4. Quick Start

```bash
python3 skills/intraday-alerts/scripts/intraday_alerts.py add --from-plan
python3 skills/intraday-alerts/scripts/intraday_alerts.py add --from-plan --plan reports/intraday_exit_plan_TSLA_2026-10-19.json
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/intraday-alerts/references/alert_rules.md`

**Scripts:**

- `skills/intraday-alerts/scripts/_market_calendar.py`
- `skills/intraday-alerts/scripts/intraday_alerts.py`

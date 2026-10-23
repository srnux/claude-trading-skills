---
name: intraday-exit-planner
description: Set the stop and the target of a day trade before the entry, so the exit is decided before the money is in. Reads the trigger from intraday-entry-timer (or a price you give), puts the stop at the opening-range midpoint by default (or the range low, a price, a percent, or a multiple of the ATR), sets the target at 2R (or 1R, or a price), adds a flat-by time, and refuses plans that make no sense. Long side only, never places an order. Use when the user asks "where's my stop", "set my stop and target", "plan the exit", "what's my R", "risk reward", or right after intraday-entry-timer triggers.
argument-hint: "[--stop or-mid|or-low|price:X|pct:X|atr:K] [--target 2R|1R|price:X]"
---

# Intraday Exit Planner

## Overview

Decide how a trade ends before it starts. The stop is where the setup has failed. The target is where the user takes what they came for. Both are set before the entry, written down and handed on, so nobody decides anything in the middle of a fast move. A stop is a plan, not a guarantee: a gap or a fast market can fill past it. Day trading loses most people money, and a neat plan does not change that.

## When to Use

- Right after `intraday-entry-timer` triggers (or with `--entry PRICE` to plan ahead at the level)
- The user asks where the stop goes, what the target is, or what the R is
- Before `intraday-time-machine`, `position-sizer --intraday-plan` and `intraday-alerts`, which all read this skill's plan

## Prerequisites

- No API key. Only an `atr:K` stop reads bars (Yahoo's free chart endpoint, or `--offline FILE`)
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for early closes

## Workflow

### Step 1: Plan from the entry report

<!-- exec: api -->
```bash
python3 skills/intraday-exit-planner/scripts/intraday_exit.py plan
python3 skills/intraday-exit-planner/scripts/intraday_exit.py plan --stop or-mid --target 1R
python3 skills/intraday-exit-planner/scripts/intraday_exit.py plan --from reports/intraday_entry_TSLA_2026-10-19.json --stop atr:1.5
```

Without `--from` it reads the newest `reports/intraday_entry_*.json`. Without an entry report give the facts as flags:

<!-- exec: api -->
```bash
python3 skills/intraday-exit-planner/scripts/intraday_exit.py plan --symbol TSLA --entry 364.18 --or-high 362.18 --or-low 354.47
python3 skills/intraday-exit-planner/scripts/intraday_exit.py plan --symbol NVDA --entry 190.25 --setup level --stop pct:1
```

Use the default stop for an opening-range breakout unless the user names another. A level setup needs one: ask.

### Step 2: Read the plan back

Read back the entry, the stop and its rule, the target and its rule, the risk a share, reward:risk and the flat-by time. Say once that the stop is a plan, not a guarantee.

### Step 3: Handle refusals

It refuses a stop at or above the entry, a target at or below it, and a stop too tight to survive the spread (risk under 0.05% of the price). If it refuses, say the reason and the fix (a wider stop, a farther target). Never loosen anything on your own. Read `references/stop_target_rules.md` for every rule and refusal.

### Step 4: Hand off

Replay it with `intraday-time-machine`, then size it with `position-sizer --intraday-plan`. Offer `intraday-alerts` for the stop, the target and the flat-by time.

Flags: `--stop or-mid|or-low|price:X|pct:X|atr:K`, `--target 2R|1R|1.5R|price:X`, `--flat-by HH:MM`, `--min-reward-risk` (1.0, warns only), `--date`, `--time`, `--entry-bar`, `--interval`, `--offline FILE`, `--now`, `--output-dir` (reports/), `--no-write`, `--json`. `show` prints the newest plan.

## Output Format

`plan` writes `reports/intraday_exit_plan_<TICKER>_<date>.json` and `.md`:

```json
{"created_by": "intraday-exit-planner", "symbol": "TSLA", "side": "buy", "date": "2026-10-19", "setup": "orb",
 "entry": 364.18, "entry_time": "10:15 AM", "entry_bar": 8, "interval": "5m",
 "opening_range": {"high": 362.18, "low": 354.47, "minutes": 15},
 "stop": 358.32, "stop_rule": "or_mid", "stop_label": "opening-range midpoint",
 "target": 370.04, "target_r": 1.0, "target_label": "1R (one times the risk)",
 "risk_per_share": 5.86, "reward_risk": 1.0, "flat_by": "15:55"}
```

Exit code 0 = a plan, 1 = refused or an error, 2 = NYSE calendar dependency missing.

## Example: TSLA on Monday 2026-10-19

Entry $364.18 at 10:15 AM (bar 8), opening range 354.47 to 362.18. `plan --stop or-mid --target 1R`:

```text
Exit plan: TSLA long, Mon 2026-10-19, opening-range breakout on 5-minute bars
  Entry         $364.18 at 10:15 AM (bar 8)
  Stop          $358.32  opening-range midpoint: ($362.18 + $354.47) / 2 = $358.325, rounded down
  Target        $370.04  1R (one times the risk)
  Risk a share  $5.86 (1.61% of the entry)
  Reward:risk   1.0
  Flat by       15:55 ET, win or lose: no overnight hold
```

The default 2R target would be 364.18 + 2 x 5.86 = 375.90. With a $50 max loss per trade, `position-sizer --intraday-plan` then sizes floor(50 / 5.86) = 8 shares.

## Resources

- `scripts/intraday_exit.py`: the exit planner CLI (`plan`, `show`)
- `scripts/_market_calendar.py`: the shared XNYS calendar (generated, do not edit)
- `references/stop_target_rules.md`: stop and target rules, rounding, refusals, flat-by and early closes

## Key Principles

1. The stop and the target are set before the entry, never after.
2. Never move a stop further from the entry once the trade is on.
3. Plain numbers only: entry, stop, target, risk a share, reward:risk. Never print a P&L or a return.
4. A 1R target is not a prediction that the price gets there.
5. Longs only.

## Safety

- Education and tooling, not financial advice. Day trading loses most people money.
- Nothing in the intraday skills places an order. An order only follows `position-sizer --intraday-plan`, `pre-trade-discipline-gate`, and an explicit yes from the user for that exact order, sent through `portfolio-manager` (Alpaca MCP, paper account first). Keep broker order tools on "Needs approval", never "Always allow".
- Longs only. No options, margin, short selling or leverage.
- Broker keys live in environment variables, never in the chat.

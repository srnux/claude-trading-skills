---
name: intraday-time-machine
description: Replay a planned day trade before risking a dollar. Takes the plan from intraday-exit-planner (entry, stop, target), rebuilds the rest of the session 10,000 times from the stock's own 5-minute bars over the last 60 days, re-runs the same opening-range rule on every past session, and prints the odds of target first, stop first or neither, the price at the close, the average R, the history and one honest verdict. Use when the user says "run the time machine", "replay this trade", "what are the odds", "simulate this trade", "monte carlo", "backtest this setup", "is this a coin flip", or after intraday-exit-planner and before position-sizer.
argument-hint: "[path to exit plan report, or TICKER]"
---

# Intraday Time Machine

## Overview

Sit between the plan and the money. `intraday-exit-planner` has set the entry, the stop and the target. Before anything is sized, ask one question: if today plays out like the stock's own last 60 days, how often does this plan hit the target first, the stop first, or neither? Answer with 10,000 replays and with the real record of the same rule on every past session. It is a simulation built from the stock's own recent bars, not a prediction. Day trading loses most people money, and a good-looking replay does not change that.

## When to Use

- After `intraday-exit-planner` writes a plan and before `position-sizer --intraday-plan` sizes it
- The user asks for the odds, a replay, a Monte Carlo of a day trade, or how often a setup hits the target
- For deeper strategy research across many days use `backtest-expert` instead: this skill answers one plan on one day

## Prerequisites

- No API key. One request to Yahoo's free chart endpoint: 60 days of 5-minute bars (`range=60d&interval=5m`), unofficial and can lag
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for early closes

## Workflow

### Step 1: Check the plan

Make sure the newest `reports/intraday_exit_plan_*.json` is today's plan from `intraday-exit-planner`. If there is none, run that first, or pass the plan as flags.

### Step 2: Run the replays

<!-- exec: api -->
```bash
python3 skills/intraday-time-machine/scripts/intraday_time_machine.py run --until 15:55
python3 skills/intraday-time-machine/scripts/intraday_time_machine.py run --plan reports/intraday_exit_plan_TSLA_2026-10-19.json
python3 skills/intraday-time-machine/scripts/intraday_time_machine.py run --symbol TSLA --date 2026-10-19 --entry 364.18 --stop 358.32 --target 370.04 --entry-time "10:15 AM"
```

Add `--until 15:55` when the plan has a flat-by time, so "neither" means still open at the time the user would get out.

### Step 3: Report in this order

The four odds, the median and the 5 to 95 range of the price at `--until`, the average R, the history line, then the verdict line and any line under it exactly as printed. Say the seed so anyone can repeat the run.

### Step 4: Be honest about the verdict

If the verdict is a coin flip or close to break-even, say so plainly. If the history and the replays disagree, say that too. Say once that this is built from the last 60 days and is not a prediction: earnings, news and halts can do things those 60 days never did. Check the stock's news (`market-news-analyst`) before going on.

### Step 5: Hand off

If the user still wants the trade, size it with `position-sizer --intraday-plan`.

Flags: `--replays` (10,000), `--seed` (19), `--window` (2 bars), `--until HH:MM`, `--offline FILE`, `--now`, `--output-dir` (reports/), `--no-write`, `--json`. `chart --from` draws an ASCII fan chart of the newest saved result. Read `references/replay_method.md` for the pool, the replay, the history and the verdict thresholds.

## Output Format

`run` writes `reports/intraday_timemachine_<TICKER>_<date>.json` and `.md`. The JSON holds `plan`, `mc` (odds, percentiles, fan-chart bands, 160 sample paths, a 24-bin histogram of the close), `history`, `verdict`, `verdict_notes` and `warnings`. Exit code 0 = a result, 1 = refused or an error, 2 = NYSE calendar dependency missing.

## Example: TSLA on Monday 2026-10-19

Entry $364.18 at 10:15 AM (bar 8), stop $358.32, target $370.04 (1R, risk $5.86 a share):

```text
10,000 replays of the rest of the session, 10:15 AM to 4:00 PM (69 five-minute bars), seed 19.
  target first   29.4 %
  stop first     25.5 %
  neither        45.1 %   still open at 4:00 PM
  green          51.7 %   target first, or above the entry at 4:00 PM
History: the same rule on each of those 59 real sessions fired 33 times:
13 target, 15 stop, 5 neither. Average R -0.062.
Close to a coin flip: target first 29.4 % vs stop first 25.5 %.
```

At 1R the target has to come first in half of the replays that hit one side. It did in 53.6%. The replays came out close to a coin flip, and the real history was slightly worse than even. That is the honest answer, and the user should hear it before anything is sized.

## Resources

- `scripts/intraday_time_machine.py`: the time machine CLI (`run`, `chart`)
- `scripts/_market_calendar.py`: the shared XNYS calendar (generated, do not edit)
- `references/replay_method.md`: the replay pool, one replay, the history replay, the verdict and the refusals

## Key Principles

1. Every number comes from the run. Never round a coin flip up into an edge.
2. Repeat the verdict line and the lines under it, never rewrite them. Never judge a 2R or 3R plan by target first vs stop first alone: the verdict already weighs the target's R.
3. Simulated odds are not predictions and not promises. Say it once, plainly.
4. Always say the seed. One plan per run: a changed entry, stop, target or date is a new run.
5. Never print a P&L or a profit.

## Safety

- Education and tooling, not financial advice. Day trading loses most people money.
- Nothing in the intraday skills places an order. An order only follows `position-sizer --intraday-plan`, `pre-trade-discipline-gate`, and an explicit yes from the user for that exact order, sent through `portfolio-manager` (Alpaca MCP, paper account first). Keep broker order tools on "Needs approval", never "Always allow".
- Longs only for live plans. No options, margin, short selling or leverage.
- Broker keys live in environment variables, never in the chat.

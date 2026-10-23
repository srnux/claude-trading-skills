---
layout: default
title: "Intraday Time Machine"
grand_parent: English
parent: Skill Guides
nav_order: 41
lang_peer: /ja/skills/intraday-time-machine/
permalink: /en/skills/intraday-time-machine/
generated: true
---

# Intraday Time Machine
{: .no_toc }

Replay a planned day trade before risking a dollar. Takes the plan from intraday-exit-planner (entry, stop, target), rebuilds the rest of the session 10,000 times from the stock's own 5-minute bars over the last 60 days, re-runs the same opening-range rule on every past session, and prints the odds of target first, stop first or neither, the price at the close, the average R, the history and one honest verdict. Use when the user says "run the time machine", "replay this trade", "what are the odds", "simulate this trade", "monte carlo", "backtest this setup", "is this a coin flip", or after intraday-exit-planner and before position-sizer.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/intraday-time-machine.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/intraday-time-machine){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Sit between the plan and the money. `intraday-exit-planner` has set the entry, the stop and the target. Before anything is sized, ask one question: if today plays out like the stock's own last 60 days, how often does this plan hit the target first, the stop first, or neither? Answer with 10,000 replays and with the real record of the same rule on every past session. It is a simulation built from the stock's own recent bars, not a prediction. Day trading loses most people money, and a good-looking replay does not change that.

---

## 2. When to Use

- After `intraday-exit-planner` writes a plan and before `position-sizer --intraday-plan` sizes it
- The user asks for the odds, a replay, a Monte Carlo of a day trade, or how often a setup hits the target
- For deeper strategy research across many days use `backtest-expert` instead: this skill answers one plan on one day

---

## 3. Prerequisites

- No API key. One request to Yahoo's free chart endpoint: 60 days of 5-minute bars (`range=60d&interval=5m`), unofficial and can lag
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for early closes

---

## 4. Quick Start

```bash
python3 skills/intraday-time-machine/scripts/intraday_time_machine.py run --until 15:55
python3 skills/intraday-time-machine/scripts/intraday_time_machine.py run --plan reports/intraday_exit_plan_TSLA_2026-10-19.json
python3 skills/intraday-time-machine/scripts/intraday_time_machine.py run --symbol TSLA --date 2026-10-19 --entry 364.18 --stop 358.32 --target 370.04 --entry-time "10:15 AM"
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/intraday-time-machine/references/replay_method.md`

**Scripts:**

- `skills/intraday-time-machine/scripts/_market_calendar.py`
- `skills/intraday-time-machine/scripts/intraday_time_machine.py`

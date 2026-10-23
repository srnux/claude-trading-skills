---
layout: default
title: "Intraday Exit Planner"
grand_parent: English
parent: Skill Guides
nav_order: 39
lang_peer: /ja/skills/intraday-exit-planner/
permalink: /en/skills/intraday-exit-planner/
generated: true
---

# Intraday Exit Planner
{: .no_toc }

Set the stop and the target of a day trade before the entry, so the exit is decided before the money is in. Reads the trigger from intraday-entry-timer (or a price you give), puts the stop at the opening-range midpoint by default (or the range low, a price, a percent, or a multiple of the ATR), sets the target at 2R (or 1R, or a price), adds a flat-by time, and refuses plans that make no sense. Long side only, never places an order. Use when the user asks "where's my stop", "set my stop and target", "plan the exit", "what's my R", "risk reward", or right after intraday-entry-timer triggers.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/intraday-exit-planner.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/intraday-exit-planner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Decide how a trade ends before it starts. The stop is where the setup has failed. The target is where the user takes what they came for. Both are set before the entry, written down and handed on, so nobody decides anything in the middle of a fast move. A stop is a plan, not a guarantee: a gap or a fast market can fill past it. Day trading loses most people money, and a neat plan does not change that.

---

## 2. When to Use

- Right after `intraday-entry-timer` triggers (or with `--entry PRICE` to plan ahead at the level)
- The user asks where the stop goes, what the target is, or what the R is
- Before `intraday-time-machine`, `position-sizer --intraday-plan` and `intraday-alerts`, which all read this skill's plan

---

## 3. Prerequisites

- No API key. Only an `atr:K` stop reads bars (Yahoo's free chart endpoint, or `--offline FILE`)
- Python 3.9+ with `pandas-market-calendars` (see `requirements.txt`) for early closes

---

## 4. Quick Start

```bash
python3 skills/intraday-exit-planner/scripts/intraday_exit.py plan
python3 skills/intraday-exit-planner/scripts/intraday_exit.py plan --stop or-mid --target 1R
python3 skills/intraday-exit-planner/scripts/intraday_exit.py plan --from reports/intraday_entry_TSLA_2026-10-19.json --stop atr:1.5
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/intraday-exit-planner/references/stop_target_rules.md`

**Scripts:**

- `skills/intraday-exit-planner/scripts/_market_calendar.py`
- `skills/intraday-exit-planner/scripts/intraday_exit.py`

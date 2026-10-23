---
name: position-sizer
description: Calculate risk-based position sizes for long stock trades. Use when user asks about position sizing, how many shares to buy, risk per trade, Kelly criterion, ATR-based sizing, fractional-share sizing, or portfolio risk allocation. Supports stop-loss distance calculation, volatility scaling, and sector concentration checks. Intraday mode sizes an intraday-exit-planner day-trade plan into one whole-share bracket order under a max loss per trade, position cap, max order and cash buffer.
---

# Position Sizer

## Overview

Calculate the optimal number of shares to buy for a long stock trade based on risk management principles. Supports three sizing methods, plus an intraday mode for day trades:

- **Fixed Fractional**: Risk a fixed percentage of account equity per trade (default: 1%)
- **ATR-Based**: Use Average True Range to set volatility-adjusted stop distances
- **Kelly Criterion**: Calculate mathematically optimal risk allocation from historical win/loss statistics

- **Intraday (`--intraday-plan`)**: Size one `intraday-exit-planner` plan into one whole-share bracket order (entry, stop-loss, take-profit) under a max loss per trade, a position cap, a max order and the cash left after a buffer

All methods apply portfolio constraints (max position %, max sector %) and output a final recommended share count with full risk breakdown. The default output is whole shares. Use `--fractional` only when the user's broker supports fractional shares for the security and order type.

## When to Use

- User asks "how many shares should I buy?"
- User wants to calculate position size for a specific trade setup
- User mentions risk per trade, stop-loss sizing, or portfolio allocation
- User asks about Kelly Criterion or ATR-based position sizing
- User has a small account where whole-share rounding would under-deploy a defined risk budget
- User wants to check if a position fits within portfolio concentration limits
- A day-trade plan from `intraday-exit-planner` needs a share count and a bracket order ("I have $5,000 and want to risk $50 a trade")

## Prerequisites

- No API keys required
- Python 3.9+ with standard library only

## Workflow

### Step 1: Gather Trade Parameters

Collect from the user:
- **Required**: Account size (total equity)
- **Mode A (Fixed Fractional)**: Entry price, stop price, risk percentage (default 1%)
- **Mode B (ATR-Based)**: Entry price, ATR value, ATR multiplier (default 2.0x), risk percentage
- **Mode C (Kelly Criterion)**: Win rate, average win, average loss; optionally entry and stop for share calculation
- **Optional constraints**: Max position % of account, max sector %, current sector exposure
- **Optional share mode**: Whole shares by default, or fractional shares with `--fractional --share-precision N` when supported by the broker
- **Mode D (Intraday)**: The plan report from `intraday-exit-planner`, the account size, and the max loss per trade (`--max-loss-usd`, or `--risk-pct` of the account). Optional: `--max-position-pct`, `--max-order-usd`, `--cash-buffer-pct`, `--available-cash`, `--min-order-usd`, `--min-reward-risk` (default 1.0)

If the user provides a stock ticker but not specific prices, use available tools to look up the current price and suggest entry/stop levels based on technical analysis.

### Step 2: Execute Position Sizer Script

Run the position sizing calculation:

```bash
# Fixed Fractional (most common)
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --output-dir reports/

# Fractional shares for small accounts or high-priced stocks
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 1000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --fractional \
  --share-precision 4 \
  --output-dir reports/

# ATR-Based
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --atr 3.20 \
  --atr-multiplier 2.0 \
  --risk-pct 1.0 \
  --output-dir reports/

# Kelly Criterion (budget mode - no entry)
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --win-rate 0.55 \
  --avg-win 2.5 \
  --avg-loss 1.0 \
  --output-dir reports/

# Kelly Criterion (shares mode - with entry/stop)
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --win-rate 0.55 \
  --avg-win 2.5 \
  --avg-loss 1.0 \
  --output-dir reports/
```

### Step 2b: Intraday Mode (day trades)

Size the newest exit plan. Ask the user for the account size and the max loss per trade if they have not given them: never size money the user has not said is for this.

<!-- exec: offline -->
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --intraday-plan reports/intraday_exit_plan_TSLA_2026-10-19.json \
  --account-size 5000 --max-loss-usd 50 \
  --max-position-pct 75 --max-order-usd 4000 --cash-buffer-pct 10 \
  --output-dir reports/

# Limit order at 364.00, and a fresh quote from intraday-alerts (used only when under 15 minutes old)
python3 skills/position-sizer/scripts/position_sizer.py \
  --intraday-plan reports/intraday_exit_plan_TSLA_2026-10-19.json \
  --account-size 5000 --max-loss-usd 50 --limit-price 364.00 \
  --prices-file state/intraday/prices.json --output-dir reports/
```

Whole shares only (a bracket order takes no fractions). The size is the smallest of four limits, and the report says which one binds:

| limit | shares |
| --- | --- |
| max loss | max loss per trade / risk a share (entry minus stop) |
| position cap | account x max position % / entry |
| max order | max order / entry |
| cash | (account, or available cash, minus the cash buffer) / entry |

It sizes at the plan's entry, the limit price with `--limit-price`, or a fresh current price when that is HIGHER than the entry (a price that ran up means a bigger loss at the same stop, a lower price never shrinks the risk). It refuses, writes the reason, writes no order and exits 1 when: the stop is too far for the max loss (zero shares), reward:risk at the sizing price is under `--min-reward-risk`, the target is at or under the entry (the move already happened), the order is under `--min-order-usd`, the plan is for another day, or the plan is a short. A stop too far away is a plain refusal, never a smaller order.

TSLA on 2026-10-19 (entry 364.18, stop 358.32, target 370.04, $5,000 account, 10% buffer, $50 max loss): max loss 50 / 5.86 = **8 shares (binds)**, position cap 10, max order 10, cash 12. 8 shares = $2,913.44, max loss at the stop 8 x 5.86 = $46.88. With the 10:52 quote of 366.48 the same plan sizes at 8.16 risk a share and reward:risk falls to 0.44: refused, because the move it was waiting for has mostly happened.

The report carries a `bracket_order` in the shape of Alpaca's `place_stock_order` (strings for qty and prices). Nothing is placed. Hand it to `pre-trade-discipline-gate`, then the user's explicit yes for that exact order, then `portfolio-manager`.

### Step 3: Load Methodology Reference

Read `references/sizing_methodologies.md` to provide context on the chosen method, risk guidelines, and portfolio constraint best practices.

### Step 4: Calculate Multiple Scenarios

If the user has not specified a single method, run multiple scenarios for comparison:
- Fixed Fractional at 0.5%, 1.0%, and 1.5% risk
- ATR-based at 1.5x, 2.0x, and 3.0x multipliers
- Present a comparison table showing shares, position value, and dollar risk for each

### Step 5: Apply Portfolio Constraints and Determine Final Size

Add constraints if the user has portfolio context:

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --max-position-pct 10 \
  --max-sector-pct 30 \
  --current-sector-exposure 22 \
  --output-dir reports/
```

Explain which constraint is binding and why it limits the position.

### Step 6: Generate Position Report

Present the final recommendation including:
- Method used and rationale
- Exact share count and position value
- Dollar risk and percentage of account
- Stop-loss price
- Any binding constraints
- Risk management reminders (portfolio heat, loss-cutting discipline)
- Small-account reminders: fractional shares do not remove broker minimums, spread/slippage, commissions/fees, margin limits, borrow availability, or day-trading controls

## Output Format

### JSON Report

```json
{
  "schema_version": "1.0",
  "mode": "shares",
  "parameters": {
    "entry_price": 155.0,
    "account_size": 100000,
    "stop_price": 148.50,
    "risk_pct": 1.0
  },
  "calculations": {
    "fixed_fractional": {
      "method": "fixed_fractional",
      "shares": 153,
      "risk_per_share": 6.50,
      "dollar_risk": 1000.0,
      "stop_price": 148.50
    },
    "atr_based": null,
    "kelly": null
  },
  "constraints_applied": [],
  "final_recommended_shares": 153,
  "final_position_value": 23715.0,
  "final_risk_dollars": 994.50,
  "final_risk_pct": 0.99,
  "binding_constraint": null
}
```

### Markdown Report

Generated automatically alongside the JSON report. Contains:
- Parameters summary
- Calculation details for the active method
- Constraints analysis (if any)
- Final recommendation with shares, value, and risk

Reports are saved to `reports/` with filenames `position_sizer_YYYY-MM-DD_HHMMSS.json` and `.md`.

## Resources

- `references/sizing_methodologies.md`: Comprehensive guide to Fixed Fractional, ATR-based, and Kelly Criterion methods with examples, comparison table, and risk management principles
- `scripts/position_sizer.py`: Main calculation script (CLI interface)
- `scripts/intraday_mode.py`: Intraday mode (plan loading, the four limits, refusals, bracket order)

## Key Principles

1. **Survival first**: Position sizing is about surviving losing streaks, not maximizing winners
2. **The 1% rule**: Default to 1% risk per trade; never exceed 2% without exceptional reason
3. **Default to whole shares**: Existing workflows remain integer-share by default
4. **Floor, never round up**: Whole-share mode floors to an integer; fractional mode floors to the requested precision so risk and concentration budgets are not exceeded
5. **Strictest constraint wins**: When multiple limits apply, the tightest one determines final size
6. **Half Kelly**: Never use full Kelly in practice; half Kelly captures 75% of growth with far less risk
7. **Portfolio heat**: Total open risk should not exceed 6-8% of account equity
8. **Intraday rules are broker-specific**: FINRA replaced the old pattern-day-trader day-count and $25,000 minimum-equity requirements with intraday margin standards effective 2026-06-04, with broker phase-in allowed through 2027-10-20. Check the broker's current rules before repeated same-day trading in a margin account.
9. **Asymmetry of losses**: A 50% loss requires a 100% gain to recover; size accordingly

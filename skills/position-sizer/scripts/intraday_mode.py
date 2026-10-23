"""Intraday mode for the position sizer.

Size one intraday-exit-planner plan (entry, stop, target, flat-by) into ONE
whole-share bracket order, inside account limits the user sets:

- max loss per trade (dollars, or --risk-pct of the account)
- position cap (percent of the account)
- max order (dollars)
- cash after a cash buffer (optionally capped by the broker's available cash)

The smallest limit wins. A stop too far away for the max loss is a plain
refusal, never a smaller order. A plan whose reward:risk falls under the
minimum at the price it would really fill at is refused. Nothing is placed:
the bracket order is a proposal in the shape of Alpaca's place_stock_order
(prices and quantities as strings) for portfolio-manager, after
pre-trade-discipline-gate and the user's explicit yes.

Standard library only. Money math in integer cents.

The sizing rules are adapted from trader-budget/size.py in day-trader-skill
(https://github.com/Jakeschincariol/day-trader-skill), Copyright (c) 2026 Jake
Schincariol, MIT License (full text in this skill's ATTRIBUTION.md).
"""

from __future__ import annotations

import datetime
import json
import math
import os
from dataclasses import dataclass

EPS = 1e-9
FRESH_MINUTES = 15
SETUP_WORDS = {"orb": "opening-range breakout", "level": "close above a level"}
LIMIT_WORDS = {
    "max_loss": "max loss per trade",
    "max_position_pct": "position cap",
    "max_order": "max order",
    "cash": "cash after the buffer",
}


class IntradaySizingError(ValueError):
    """A plan or a limit that cannot be sized (one plain line for the user)."""


@dataclass
class IntradayLimits:
    account_size: float
    max_loss_usd: float | None = None
    risk_pct: float | None = None
    max_position_pct: float | None = None
    max_order_usd: float | None = None
    cash_buffer_pct: float = 0.0
    available_cash: float | None = None
    min_order_usd: float = 0.0
    min_reward_risk: float | None = 1.0


# ---------------------------------------------------------------- time (New York, no tz files)


def _nth_sunday(year: int, month: int, n: int) -> datetime.date:
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def new_york_date(now_utc: datetime.datetime) -> str:
    """Naive UTC -> the New York calendar date (US DST rule since 2007, no tz files)."""
    y = now_utc.year
    start = datetime.datetime.combine(_nth_sunday(y, 3, 2), datetime.time(7, 0))
    end = datetime.datetime.combine(_nth_sunday(y, 11, 1), datetime.time(6, 0))
    offset = -4 if start <= now_utc.replace(tzinfo=None) < end else -5
    return (now_utc.replace(tzinfo=None) + datetime.timedelta(hours=offset)).date().isoformat()


def parse_utc(text: str | None) -> datetime.datetime | None:
    """ISO time -> naive UTC. A time without an offset is taken as UTC. None on bad input."""
    if not text:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = (dt - dt.utcoffset()).replace(tzinfo=None)
    return dt


# ---------------------------------------------------------------- inputs


def load_plan(path: str) -> dict:
    """An intraday-exit-planner report (reports/intraday_exit_plan_<TICKER>_<date>.json)."""
    if not path or not os.path.exists(path):
        raise IntradaySizingError(
            f"no plan at {path}: run intraday-exit-planner first (it writes "
            "reports/intraday_exit_plan_<TICKER>_<date>.json)"
        )
    try:
        with open(path, encoding="utf-8") as fh:
            plan = json.load(fh)
    except ValueError as e:
        raise IntradaySizingError(f"{path} is not valid JSON: {e}")
    if not isinstance(plan, dict):
        raise IntradaySizingError(f"{path} is not a plan (expected a JSON object)")
    return plan


def load_prices(path: str) -> dict:
    """The intraday-alerts prices file (state/intraday/prices.json), or {} when absent."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except ValueError as e:
        raise IntradaySizingError(f"{path} is not valid JSON: {e}")
    return doc if isinstance(doc, dict) else {}


def fresh_price(doc: dict, symbol: str, now_utc: datetime.datetime, minutes: int = FRESH_MINUTES):
    """(price, fresh) for symbol from a prices document. Fresh = quoted within `minutes`."""
    try:
        price = float((doc.get("prices") or {}).get(symbol))
    except (TypeError, ValueError):
        return None, False
    if not price > 0:
        return None, False
    detail = (doc.get("detail") or {}).get(symbol) or {}
    when = (
        parse_utc(detail.get("time"))
        or parse_utc(detail.get("fetched"))
        or parse_utc(doc.get("as_of"))
    )
    if when is None:
        return price, False
    age = (now_utc - when).total_seconds()
    return price, -60 <= age <= minutes * 60


# ---------------------------------------------------------------- money


def _num(x) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def round_cent(x: float) -> float:
    """Round a price to the cent, half up."""
    return math.floor(float(x) * 100 + 0.5 + EPS) / 100.0


def cents(x: float) -> int:
    return int(round(float(x) * 100))


def shares_for(usd: float, per_share: float) -> int:
    """Whole shares that fit in usd at per_share, in exact integer cents."""
    u, p = cents(usd), cents(per_share)
    if p <= 0 or u <= 0:
        return 0
    return u // p


def money(x: float) -> str:
    return f"${float(x):,.2f}"


def ratio_str(x: float) -> str:
    """1 -> "1.0", 1.5 -> "1.5", 1.25 -> "1.25"."""
    text = f"{float(x):.2f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def price_str(x: float) -> str:
    """358.32 -> "358.32": Alpaca wants prices as strings."""
    return f"{round_cent(x):.2f}"


# ---------------------------------------------------------------- sizing


def _check_limits(lim: IntradayLimits) -> float:
    """Validate the limits and return the max loss per trade in dollars."""
    if not (_num(lim.account_size) or 0) > 0:
        raise IntradaySizingError("account size must be positive")
    if lim.max_loss_usd is not None:
        max_loss = _num(lim.max_loss_usd)
        if max_loss is None or max_loss <= 0:
            raise IntradaySizingError("max loss per trade must be a positive dollar amount")
    elif lim.risk_pct is not None:
        pct = _num(lim.risk_pct)
        if pct is None or pct <= 0:
            raise IntradaySizingError("risk_pct must be positive")
        max_loss = round(lim.account_size * pct / 100.0, 2)
    else:
        raise IntradaySizingError(
            "intraday mode needs --max-loss-usd or --risk-pct (the most one trade may lose at the stop)"
        )
    buf = _num(lim.cash_buffer_pct)
    if buf is None or not 0 <= buf < 100:
        raise IntradaySizingError("cash buffer must be between 0 and 100 percent")
    for name in ("max_position_pct", "max_order_usd", "available_cash"):
        v = getattr(lim, name)
        if v is not None and not (_num(v) or 0) > 0:
            raise IntradaySizingError(f"{name} must be positive")
    if lim.min_reward_risk is not None and (
        _num(lim.min_reward_risk) is None or lim.min_reward_risk < 0
    ):
        raise IntradaySizingError("min_reward_risk must be zero or positive")
    return max_loss


def _check_plan(plan: dict, today: str | None):
    sym = str(plan.get("symbol") or "").strip().upper()
    if not sym:
        raise IntradaySizingError("the plan has no symbol (run intraday-exit-planner)")
    side = str(plan.get("side") or "buy").strip().lower()
    if side not in ("buy", "long"):
        raise IntradaySizingError(
            f"intraday mode sizes long (buy) day trades only, the plan says {side!r}"
        )
    if today and plan.get("date") and str(plan["date"]) != today:
        raise IntradaySizingError(
            f"the plan is for {plan['date']} and today is {today} in New York: "
            "make a new plan with intraday-exit-planner"
        )
    vals = {}
    for name in ("entry", "stop", "target"):
        v = _num(plan.get(name))
        if v is None or v <= 0:
            raise IntradaySizingError(
                f"the plan needs a positive {name} (run intraday-exit-planner): "
                "a bracket order needs entry, stop and target"
            )
        vals[name] = round_cent(v)
    return sym, vals["entry"], vals["stop"], vals["target"]


def size_intraday(
    plan: dict,
    limits: IntradayLimits,
    limit_price: float | None = None,
    current_price: float | None = None,
    today: str | None = None,
) -> dict:
    """Pure function: one plan + the account limits -> the sizing result (a dict).

    limit_price    size and send a limit order at this price (None = market order)
    current_price  a FRESH latest price. A market order is sized at the higher of it and the
                   plan's entry: a price that ran up means a bigger loss at the same stop.
    today          New York date YYYY-MM-DD. A plan for another day is refused.
    """
    if not isinstance(plan, dict):
        raise IntradaySizingError("the plan is not a JSON object")
    max_loss = _check_limits(limits)
    sym, entry_plan, stop, target = _check_plan(plan, today)

    if limit_price is not None:
        ref, ref_from = round_cent(limit_price), "limit"
    elif current_price is not None and round_cent(current_price) > entry_plan:
        ref, ref_from = round_cent(current_price), "current_price"
    else:
        ref, ref_from = entry_plan, "plan"
    if stop >= ref:
        raise IntradaySizingError(
            f"the stop {price_str(stop)} is not below the entry {price_str(ref)}: "
            "a long trade needs its stop underneath"
        )
    risk_c, reward_c = cents(ref - stop), cents(target - ref)
    risk = risk_c / 100.0

    account = float(limits.account_size)
    buffer_usd = round(account * float(limits.cash_buffer_pct) / 100.0, 2)
    available = account - buffer_usd
    cash_how = f"account {money(account)} minus the {money(buffer_usd)} buffer"
    if limits.available_cash is not None and limits.available_cash - buffer_usd < available - 0.005:
        available = limits.available_cash - buffer_usd
        cash_how = (
            f"available cash {money(limits.available_cash)} minus the {money(buffer_usd)} buffer"
        )
    available = max(round(available, 2), 0.0)

    constraints = [
        {
            "type": "max_loss",
            "limit_usd": max_loss,
            "max_shares": shares_for(max_loss, risk),
            "how": f"{money(max_loss)} max loss / {price_str(risk)} risk a share",
        }
    ]
    if limits.max_position_pct:
        cap = round(account * limits.max_position_pct / 100.0, 2)
        constraints.append(
            {
                "type": "max_position_pct",
                "limit": limits.max_position_pct,
                "limit_usd": cap,
                "max_shares": shares_for(cap, ref),
                "how": f"{limits.max_position_pct:g}% of {money(account)} = {money(cap)} / {price_str(ref)}",
            }
        )
    if limits.max_order_usd:
        constraints.append(
            {
                "type": "max_order",
                "limit_usd": limits.max_order_usd,
                "max_shares": shares_for(limits.max_order_usd, ref),
                "how": f"{money(limits.max_order_usd)} / {price_str(ref)}",
            }
        )
    constraints.append(
        {
            "type": "cash",
            "limit_usd": available,
            "max_shares": shares_for(available, ref),
            "how": f"{cash_how} = {money(available)} / {price_str(ref)}",
        }
    )
    qty = max(0, min(c["max_shares"] for c in constraints))
    binding = next(c["type"] for c in constraints if c["max_shares"] == qty)
    for c in constraints:
        c["binding"] = c["type"] == binding
    cost = round(qty * ref, 2)
    loss = round(qty * risk_c / 100.0, 2)
    reward_risk = round(reward_c / float(risk_c), 2)

    refusal = None
    if target <= ref:
        refusal = (
            f"the target {price_str(target)} is not above the entry {price_str(ref)}: "
            "the move has already happened. No order. Skip it, or make a new plan with intraday-exit-planner."
        )
    elif qty == 0 and binding == "max_loss":
        refusal = (
            f"one share risks {money(risk)} (entry {price_str(ref)} minus stop {price_str(stop)}), "
            f"more than your {money(max_loss)} max loss per trade. No order. Skip this trade, "
            "or plan a closer stop with intraday-exit-planner."
        )
    elif qty == 0:
        how = next(c["how"] for c in constraints if c["type"] == binding)
        refusal = f"one share of {sym} costs {money(ref)}, more than your {LIMIT_WORDS[binding]} ({how}). No order."
    elif limits.min_reward_risk and reward_c < limits.min_reward_risk * risk_c - EPS:
        refusal = (
            f"reward:risk {reward_c / float(risk_c):.2f} (target {price_str(target)}, entry {price_str(ref)}, "
            f"stop {price_str(stop)}) is under your minimum {ratio_str(limits.min_reward_risk)}. No order. "
            "Skip it, or make a new plan with intraday-exit-planner."
        )
    elif cost < float(limits.min_order_usd or 0) - 0.005:
        refusal = (
            f"{qty} share{'' if qty == 1 else 's'} of {sym} is {money(cost)}, "
            f"under your {money(limits.min_order_usd)} minimum order. No order."
        )
    final_qty = 0 if refusal else qty

    result = {
        "schema_version": "1.0",
        "mode": "intraday",
        "parameters": {
            "symbol": sym,
            "side": "buy",
            "date": plan.get("date"),
            "setup": plan.get("setup") or "",
            "entry_time": plan.get("entry_time") or "",
            "entry_plan": entry_plan,
            "sized_at": ref,
            "sized_from": ref_from,
            "stop_price": stop,
            "target_price": target,
            "risk_per_share": risk,
            "reward_risk": reward_risk,
            "flat_by": plan.get("flat_by"),
            "account_size": account,
            "max_loss_usd": max_loss,
            "cash_buffer_pct": float(limits.cash_buffer_pct),
            "cash_buffer_usd": buffer_usd,
            "min_reward_risk": limits.min_reward_risk,
            "order_type": "limit" if limit_price is not None else "market",
            "stop_label": plan.get("stop_label") or "",
            "target_label": plan.get("target_label") or "",
        },
        "constraints_applied": constraints,
        "final_recommended_shares": final_qty,
        "final_position_value": round(final_qty * ref, 2),
        "final_risk_dollars": round(final_qty * risk_c / 100.0, 2),
        "final_risk_pct": round(final_qty * risk_c / 100.0 / account * 100, 2),
        "binding_constraint": binding,
        "shares_before_refusal": qty,
        "max_loss_at_stop": loss if not refusal else 0.0,
        "refusal": refusal,
    }
    result["bracket_order"] = bracket_order(result)
    return result


def bracket_order(result: dict) -> dict | None:
    """The one proposed order: Alpaca place_stock_order fields (strings) plus why and plan notes."""
    if result.get("refusal") or not result.get("final_recommended_shares"):
        return None
    p = result["parameters"]
    qty = int(result["final_recommended_shares"])
    order = {
        "symbol": p["symbol"],
        "side": "buy",
        "qty": str(qty),
        "type": p["order_type"],
        "time_in_force": "day",
    }
    if p["order_type"] == "limit":
        order["limit_price"] = price_str(p["sized_at"])
    words = dict(
        LIMIT_WORDS, max_loss=f"{money(p['max_loss_usd']).replace('.00', '')} max loss per trade"
    )
    setup = SETUP_WORDS.get(p["setup"], p["setup"] or "day trade")
    order.update(
        {
            "order_class": "bracket",
            "take_profit_limit_price": price_str(p["target_price"]),
            "stop_loss_stop_price": price_str(p["stop_price"]),
            "why": (
                f"{setup} on {p['symbol']}: {qty} shares, bound by your {words[result['binding_constraint']]} "
                f"({qty} x {price_str(p['risk_per_share'])} = {money(result['max_loss_at_stop'])} at the stop)"
            ),
            "plan": {
                "entry": p["sized_at"],
                "stop": p["stop_price"],
                "target": p["target_price"],
                "risk_per_share": p["risk_per_share"],
                "max_loss": result["max_loss_at_stop"],
                "setup": p["setup"],
                "entry_time": p["entry_time"],
                "flat_by": p["flat_by"],
            },
        }
    )
    return order


def markdown_lines(result: dict) -> list[str]:
    """The intraday part of the position sizer's Markdown report."""
    p = result["parameters"]
    lines = [
        "## Intraday Plan",
        f"- **Trade:** {p['symbol']} buy, {SETUP_WORDS.get(p['setup'], p['setup'] or 'setup')}, "
        f"{p['date']} {p['entry_time']}".rstrip(),
        f"- **Sized at:** {price_str(p['sized_at'])} ({p['sized_from'].replace('_', ' ')})",
        f"- **Stop:** {price_str(p['stop_price'])}  **Target:** {price_str(p['target_price'])}",
        f"- **Risk a share:** {price_str(p['risk_per_share'])}  **Reward:risk:** {p['reward_risk']:.2f}",
        f"- **Flat by:** {p['flat_by'] or 'not set'} New York",
        "",
        "## Limits (whole shares, the smallest one wins)",
        "| Limit | How | Shares | Binds |",
        "|---|---|---|---|",
    ]
    for c in result["constraints_applied"]:
        lines.append(
            f"| {c['type']} | {c['how']} | {c['max_shares']} | {'yes' if c['binding'] else ''} |"
        )
    lines.append("")
    order = result.get("bracket_order")
    if order is None:
        lines.append(f"No order: {result['refusal']}")
        return lines
    qty = result["final_recommended_shares"]
    lines += [
        f"- **Shares:** {qty} = {money(result['final_position_value'])}",
        f"- Max loss at the stop: {qty} x {price_str(p['risk_per_share'])} = {money(result['max_loss_at_stop'])}",
        "- A stop is an order, not a promise: in a fast market it can fill below the stop.",
        "",
        "## Proposed Bracket Order",
        "Nothing has been placed. These are place_stock_order arguments for portfolio-manager, "
        "after pre-trade-discipline-gate and your explicit yes.",
        "",
        "- buy {} {}, {}, day, take-profit {}, stop-loss {}".format(
            order["qty"],
            order["symbol"],
            f"limit {order['limit_price']}" if order["type"] == "limit" else "market",
            order["take_profit_limit_price"],
            order["stop_loss_stop_price"],
        ),
        f"- {order['why']}",
    ]
    return lines

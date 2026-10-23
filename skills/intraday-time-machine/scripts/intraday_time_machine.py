#!/usr/bin/env python3
"""intraday-time-machine: replay a planned day trade before you risk a dollar.

Replays a planned day trade before you risk a dollar: 10,000 simulated runs of
the rest of the session from your entry, plus the same rule on every past
session in the data.

    python3 intraday_time_machine.py run                # newest exit plan report, 10,000 replays, seed 19
    python3 intraday_time_machine.py run --no-write     # print only, no report
    python3 intraday_time_machine.py run --until 15:55            # stop each replay at your flat-by time
    python3 intraday_time_machine.py run --seed 7 --replays 20000 --json
    python3 intraday_time_machine.py run --symbol TSLA --date 2026-10-19 --entry 364.18 \\
        --stop 358.32 --target 370.04 --entry-time "10:15 AM"
    python3 intraday_time_machine.py chart                        # ASCII fan chart of the replays
    python3 intraday_time_machine.py chart --from reports/intraday_timemachine_TSLA_2026-10-19.json

How the replays work (deterministic for a given --seed):
  1. Fetch 60 days of 5-minute bars (Yahoo v8 chart, range=60d interval=5m;
     one request). Keep only FULL sessions before the plan's date: 78 bars,
     9:30 to 4:00 New York time. Half days, gaps and today are left out.
  2. The pool: for every bar slot 1..77 of the day, each past session's bar as
     ratios to the previous bar's close: (open, high, low, close) / prev close.
  3. One replay starts at the entry price and walks the rest of the session.
     For each bar i it picks a slot j = i + randint(-window, window), kept in
     1..77, then one past bar from pool[j] (random.choice), and scales it to
     the current price. The stop is checked before the target in every bar,
     so a bar that touches both counts as the stop (the conservative call).
  4. Outcomes: "target" or "stop" (whichever was touched first), or "neither"
     when the trade is still open at --until (default 16:00, the close, or
     13:00 on an NYSE early-close day).
     "green" = target first, or above the entry at --until (below for a sell).
     R = the target's R at the target, -1 at the stop, otherwise
     (price at --until - entry) / risk. A gap through the stop still counts
     -1R here; a real fill can be worse.
  5. The price at --until: median and the 5th to 95th percentile of all
     replays (pct(a, q) = sorted a at index int(q * n)). The fan chart uses a
     second run of 2,000 paths with the same seed. The histogram has 24 bins
     between the 1st and 99th percentile.
  6. History: the plan's own rule (an opening-range breakout with the same
     opening range, stop rule and target R) re-run on every one of those past
     full sessions, first close beyond the range = entry, same stop-first rule.

The verdict line looks at the replays that hit one side (target or stop) and
compares the target's share of them, target / (target + stop), with the share
that breaks even at the plan's target R: 1 / (1 + R), so 50 % at 1R and 33 % at
2R. The gap, in percentage points:
  less than 5 points    "Close to a coin flip" (1R) / "Close to break-even" (other R)
  5 to 15 points        "Leans toward the target" / "Leans toward the stop"
  15 points or more     "Strongly toward the target" / "Strongly toward the stop"
Below it: a note when more than 40 % of the replays hit neither (the price at
--until decides those), and the average R when its sign goes against the lean.

5-minute bars only: Yahoo keeps 60 days of 5-min bars but only about 7 days of
1-min bars, too few sessions for a fair pool. The run refuses with a plain
message when there are fewer than 20 full sessions or the entry bar is not in
the data. Same plan, same data and same --seed give the same numbers on any
machine. A simulation built from the stock's own recent bars is not a
prediction: earnings, news and halts can do what the last 60 days never did.

Data: https://query2.finance.yahoo.com/v8/finance/chart/<T>?range=60d&interval=5m
(unofficial and free, can lag; falls back to query1 on 429 or 5xx).
--offline FILE reads a saved chart JSON (.json or .json.gz) instead.
Times are New York (ET) wall-clock; --now "2026-10-19 10:15" pins the clock.
"""

import argparse
import datetime
import functools
import glob
import gzip
import json
import math
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import _market_calendar

UA = "Mozilla/5.0 (compatible; claude-trading-skills intraday-time-machine)"
DEFAULT_OUTPUT_DIR = "reports/"
PAUSE = 0.5  # seconds between requests: be polite to free endpoints
BACKOFF = 5.0  # seconds to wait once after a 429
HOSTS = ("query2", "query1")
INTERVAL = 300  # 5-minute bars, in seconds
SESSION_BARS = 78  # 9:30 to 16:00 in 5-minute bars
OPEN_MIN = 9 * 60 + 30
CLOSE_MIN = 16 * 60
MIN_SESSIONS = 20
SAMPLE_PATHS = 160
BAND_PATHS = 2000
BAND_Q = (0.05, 0.25, 0.5, 0.75, 0.95)
HIST_BINS = 24
COIN_FLIP = 0.05  # verdict thresholds, see the docstring
STRONG = 0.15
MANY_NEITHER = 0.40
EPOCH = datetime.datetime(1970, 1, 1)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class TMError(Exception):
    pass


class CalendarMissing(Exception):
    """The shared NYSE calendar could not be loaded (exit code 2)."""


@functools.lru_cache(maxsize=256)
def nyse_close_minute(iso_day):
    """The NYSE close that day in minutes after midnight, New York time (16:00 or an early close).

    It comes from the repository's shared cash-equity calendar (_market_calendar.py), so
    early closes never go stale. A day the NYSE is closed keeps the regular 16:00 close:
    the time machine then refuses the plan because the entry bar is not in the data."""
    try:
        s = _market_calendar.session_for_date("XNYS", datetime.date.fromisoformat(iso_day))
    except _market_calendar.CalendarUnavailableError as e:
        raise CalendarMissing(
            f"the NYSE calendar is unavailable ({e}). Install the skill's requirements.txt"
        )
    if s is None:
        return CLOSE_MIN
    t = s.market_close.time()
    return t.hour * 60 + t.minute


# ---------------------------------------------------------------- time (same helpers as intraday-alerts)


def _nth_sunday(year, month, n):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def eastern_offset(utc):
    """Hours from UTC for New York: -4 in daylight time, -5 otherwise.
    DST runs from 2:00 a.m. on the second Sunday of March to 2:00 a.m. on the
    first Sunday of November (US rule since 2007)."""
    y = utc.year
    start = datetime.datetime.combine(_nth_sunday(y, 3, 2), datetime.time(7, 0))  # 2:00 EST
    end = datetime.datetime.combine(_nth_sunday(y, 11, 1), datetime.time(6, 0))  # 2:00 EDT
    naive = utc.replace(tzinfo=None)
    return -4 if start <= naive < end else -5


def to_eastern(utc):
    return utc.replace(tzinfo=None) + datetime.timedelta(hours=eastern_offset(utc))


def eastern_to_utc(local):
    for off in (-4, -5):
        utc = local - datetime.timedelta(hours=off)
        if eastern_offset(utc) == off:
            return utc
    return local + datetime.timedelta(hours=5)


def parse_now(text):
    """ISO time -> naive UTC. A time without an offset is taken as New York time."""
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise TMError('--now wants a time like "2026-10-19 10:15" (New York) or ...Z (UTC)')
    if dt.tzinfo is None:
        return eastern_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def utc_of(ts):
    return EPOCH + datetime.timedelta(seconds=int(ts))


def parse_clock(text, what):
    """'10:15 AM', '10:15am', '15:55' or '3:55' (a bare 1 to 8 o'clock means p.m.) -> minutes after midnight."""
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*(?:([AaPp])\.?\s*[Mm]\.?)?\s*$", str(text or ""))
    if not m:
        raise TMError(f"{what} wants a New York time like 10:15 AM or 15:55, not {text!r}")
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if mi > 59 or h > 23 or (ap and not 1 <= h <= 12):
        raise TMError(f"{what} {text!r} is not a clock time")
    if ap == "p" and h != 12:
        h += 12
    elif ap == "a" and h == 12:
        h = 0
    elif not ap and 1 <= h <= 8:
        h += 12
    return h * 60 + mi


def clock12(minutes):
    h, m = divmod(minutes, 60)
    return "{:d}:{:02d} {}".format(h % 12 or 12, m, "AM" if h < 12 else "PM")


def clock24(minutes):
    return "{:02d}:{:02d}".format(*divmod(minutes, 60))


# ---------------------------------------------------------------- data


def chart_url(sym, host="query2"):
    return "https://{}.finance.yahoo.com/v8/finance/chart/{}?range=60d&interval=5m".format(
        host, urllib.parse.quote(sym.upper().replace(".", "-"))
    )


def _sleep(seconds):
    time.sleep(seconds)


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_chart(sym):
    """One request for 60 days of 5-min bars. query2 first, one retry after a 429,
    then query1 on 429 or 5xx."""
    last = None
    for n, host in enumerate(HOSTS):
        if n:
            _sleep(PAUSE)
        for attempt in (0, 1):
            url = chart_url(sym, host)
            try:
                return _get(url)
            except urllib.error.HTTPError as e:
                last = e.code
                try:
                    e.close()
                except Exception:
                    pass
                if e.code == 429 and attempt == 0:
                    _sleep(BACKOFF)
                    continue
                if e.code == 429 or e.code >= 500:
                    break
                if e.code == 404:
                    raise TMError(
                        f"Yahoo has no chart for {sym.upper()} (HTTP 404): check the ticker"
                    )
                raise TMError(f"Yahoo answered HTTP {e.code:d} for {sym.upper()}")
            except urllib.error.URLError as e:
                raise TMError(f"could not reach Yahoo: {e.reason}")
            except OSError as e:
                raise TMError(f"could not reach Yahoo: {e}")
    if last == 429:
        raise TMError("Yahoo is rate limiting (HTTP 429). Wait a minute and run it again.")
    raise TMError(f"Yahoo answered HTTP {last} for {sym.upper()} on both hosts. Try again later.")


def read_offline(path, sym):
    """A saved Yahoo chart file (.json or .json.gz), or a folder holding <SYM>-60d5m.json(.gz)."""
    if os.path.isdir(path):
        for name in (f"{sym.upper()}-60d5m.json", f"{sym.upper()}-60d5m.json.gz"):
            if os.path.exists(os.path.join(path, name)):
                path = os.path.join(path, name)
                break
        else:
            raise TMError(f"no {sym.upper()}-60d5m.json(.gz) in {path}")
    if not os.path.exists(path):
        raise TMError(f"no offline chart file {path}")
    opener = gzip.open if path.endswith(".gz") else open
    try:
        with opener(path, "rt", encoding="utf-8") as fh:
            return fh.read()
    except OSError as e:
        raise TMError(f"could not read {path}: {e}")


def chart_result(text, sym):
    try:
        data = json.loads(text)
    except ValueError:
        raise TMError(f"Yahoo returned something that is not JSON for {sym.upper()}")
    chart = data.get("chart") if isinstance(data, dict) else None
    if not isinstance(chart, dict):
        raise TMError(f"Yahoo returned something unexpected for {sym.upper()}")
    res = chart.get("result")
    if not res:
        err = chart.get("error") or {}
        raise TMError(
            "Yahoo has no data for {}: {}".format(
                sym.upper(), err.get("description") or "unknown ticker"
            )
        )
    return res[0]


def parse_bars(result, now_utc):
    """Yahoo chart result -> (meta, bars, dropped). Regular-session 5-min bars only,
    oldest first. Dropped: bars with a missing price, bars off the 5-minute grid
    (the live tick, e.g. 10:49:45), bars not complete yet (now < start + 5 min,
    where now is the earlier of --now and the data's own regularMarketTime), and
    bars outside 9:30 to 16:00 New York time."""
    meta = result.get("meta") or {}
    stamps = result.get("timestamp") or []
    q = ((result.get("indicators") or {}).get("quote") or [{}])[0] or {}
    cols = [q.get(k) or [] for k in ("open", "high", "low", "close", "volume")]
    as_of = now_utc
    rmt = meta.get("regularMarketTime")
    if isinstance(rmt, (int, float)) and utc_of(rmt) < as_of:
        as_of = utc_of(rmt)
    dropped = {"no_price": 0, "off_grid": 0, "not_complete": 0, "outside_hours": 0}
    bars = {}
    for i, ts in enumerate(stamps):
        o, h, lw, c, v = [col[i] if i < len(col) else None for col in cols]
        if ts is None or None in (o, h, lw, c):
            dropped["no_price"] += 1
            continue
        ts = int(ts)
        if ts % INTERVAL:
            dropped["off_grid"] += 1
            continue
        start = utc_of(ts)
        local = to_eastern(start)
        mins = local.hour * 60 + local.minute - OPEN_MIN
        if mins < 0 or mins >= SESSION_BARS * 5:
            dropped["outside_hours"] += 1
            continue
        if start + datetime.timedelta(seconds=INTERVAL) > as_of:
            dropped["not_complete"] += 1
            continue
        bars[ts] = {
            "date": local.date().isoformat(),
            "slot": mins // 5,
            "start": local.strftime("%H:%M"),
            "o": o,
            "h": h,
            "l": lw,
            "c": c,
            "v": v or 0,
        }
    return meta, [bars[t] for t in sorted(bars)], dropped


def split_sessions(bars):
    """{date: {slot: bar}}."""
    days = {}
    for b in bars:
        days.setdefault(b["date"], {})[b["slot"]] = b
    return days


def full_sessions(days, before):
    """Full sessions (all 78 bars) strictly before the plan's date, oldest first,
    and the short ones that were left out (half days, gaps)."""
    full, short = [], []
    for d in sorted(days):
        if d >= before:
            continue
        s = days[d]
        if len(s) == SESSION_BARS:
            full.append((d, [s[i] for i in range(SESSION_BARS)]))
        else:
            short.append({"date": d, "bars": len(s)})
    return full, short


# ---------------------------------------------------------------- the simulation (sim.py)


def build_pool(sessions):
    """pool[i] = every past session's bar i as (o, h, l, c) / bar i-1's close, in date order."""
    pool = [[] for _ in range(SESSION_BARS)]
    for _, D in sessions:
        for i in range(1, SESSION_BARS):
            pc = D[i - 1]["c"]
            pool[i].append((D[i]["o"] / pc, D[i]["h"] / pc, D[i]["l"] / pc, D[i]["c"] / pc))
    return pool


def pct(a, q):
    return a[min(len(a) - 1, int(q * len(a)))]


def simulate(pool, entry, stop, target, k, last, replays=10000, seed=19, window=2, side="buy"):
    """Monte Carlo replays of bars k+1..last. Same draws and order for the same --seed."""
    long = side == "buy"
    risk = (entry - stop) if long else (stop - entry)
    r_target = round(((target - entry) if long else (entry - target)) / risk, 4)

    def slot(rng, i):
        return i if window == 0 else min(SESSION_BARS - 1, max(1, i + rng.randint(-window, window)))

    rng = random.Random(seed)
    choice = rng.choice
    outcomes, closes, paths = [], [], []
    for n in range(replays):
        p = entry
        outcome = None
        keep = n < SAMPLE_PATHS
        path = [entry]
        for i in range(k + 1, last + 1):
            o, h, lw, c = choice(pool[slot(rng, i)])
            hi, lo, cl = p * h, p * lw, p * c
            if outcome is None:
                if long:
                    if lo <= stop:
                        outcome = "stop"  # both inside one bar: count the loss (conservative)
                    elif hi >= target:
                        outcome = "target"
                else:
                    if hi >= stop:
                        outcome = "stop"
                    elif lo <= target:
                        outcome = "target"
            p = cl
            if keep:
                path.append(round(p, 2))
        outcomes.append(outcome or "close")
        closes.append(p)
        if keep:
            paths.append(path)
    cnt = {x: outcomes.count(x) for x in ("target", "stop", "close")}
    green = sum(
        1
        for o, p in zip(outcomes, closes)
        if o == "target" or (o == "close" and (p > entry if long else p < entry))
    )
    Rs = [
        r_target
        if o == "target"
        else -1.0
        if o == "stop"
        else ((p - entry) if long else (entry - p)) / risk
        for o, p in zip(outcomes, closes)
    ]
    srt = sorted(closes)
    # percentile bands per bar for the fan chart: a second run of 2,000 paths, same seed
    rng = random.Random(seed)
    choice = rng.choice
    allp = []
    for n in range(BAND_PATHS):
        p = entry
        path = [entry]
        for i in range(k + 1, last + 1):
            o, h, lw, c = choice(pool[slot(rng, i)])
            p = p * c
            path.append(p)
        allp.append(path)
    bands = []
    for j in range(last - k + 1):
        col = sorted(pp[j] for pp in allp)
        bands.append([round(pct(col, q), 2) for q in BAND_Q])
    lo_, hi_ = pct(srt, 0.01), pct(srt, 0.99)
    W = (hi_ - lo_) / HIST_BINS
    bins = [0] * HIST_BINS
    for c in srt:
        b = int((c - lo_) / W) if W > 0 else 0
        if 0 <= b < HIST_BINS:
            bins[b] += 1
    return {
        "replays": replays,
        "seed": seed,
        "window": window,
        "bars_left": last - k,
        "p_target": round(cnt["target"] / replays, 4),
        "p_stop": round(cnt["stop"] / replays, 4),
        "p_neither": round(cnt["close"] / replays, 4),
        "p_green": round(green / replays, 4),
        "median_close": round(pct(srt, 0.5), 2),
        "p5_close": round(pct(srt, 0.05), 2),
        "p95_close": round(pct(srt, 0.95), 2),
        "avg_R": round(statistics.mean(Rs), 3),
        "r_at_target": r_target,
        "band_paths": BAND_PATHS,
        "bands": bands,
        "sample_paths": paths,
        "hist": {"lo": round(lo_, 2), "hi": round(hi_, 2), "bins": bins},
    }


# ---------------------------------------------------------------- stop rules and the history replay


def cents_away(x, long):
    """Round a stop to the cent, away from the entry: down for a buy, up for a sell."""
    c = round(x * 100, 4)
    return (math.floor(c) if long else math.ceil(c)) / 100.0


def opening_range(D, n):
    """(high, low) of the first n bars of a session given as {slot: bar} or a list."""
    rows = [D[i] for i in range(n)]
    return max(b["h"] for b in rows), min(b["l"] for b in rows)


def rule_stop(rule, oh, ol, entry, long):
    r = rule["stop_rule"]
    if r == "or_mid":
        return cents_away((oh + ol) / 2, long)
    if r in ("or_low", "or_high"):
        return cents_away(ol if long else oh, long)
    frac = rule["stop_pct"] / 100.0
    return cents_away(entry * (1 - frac) if long else entry * (1 + frac), long)


def history_replay(sessions, rule, last, side="buy"):
    """The plan's rule on every past full session: entry = the first bar after the
    opening range to close beyond it (up to the --until bar), then stop first, then
    target, bar by bar, else the close at --until."""
    long = side == "buy"
    n = rule["or_minutes"] // 5
    trades = []
    for d, D in sessions:
        oh, ol = opening_range(D, n)
        kk = next(
            (i for i in range(n, last + 1) if (D[i]["c"] > oh if long else D[i]["c"] < ol)), None
        )
        if kk is None:
            continue
        e = round(D[kk]["c"], 2)
        s = rule_stop(rule, oh, ol, e, long)
        risk = (e - s) if long else (s - e)
        if risk <= 0:
            continue
        t = round(e + rule["target_r"] * risk, 2) if long else round(e - rule["target_r"] * risk, 2)
        oc = None
        for b in D[kk + 1 : last + 1]:
            if (b["l"] <= s) if long else (b["h"] >= s):
                oc = "stop"
                break
            if (b["h"] >= t) if long else (b["l"] <= t):
                oc = "target"
                break
        cl = D[last]["c"]
        R = (
            ((t - e) if long else (e - t)) / risk
            if oc == "target"
            else -1.0
            if oc == "stop"
            else ((cl - e) if long else (e - cl)) / risk
        )
        trades.append(
            {
                "date": d,
                "time": clock12(OPEN_MIN + 5 * (kk + 1)),
                "entry": e,
                "stop": s,
                "target": t,
                "outcome": oc or "close",
                "R": round(R, 2),
            }
        )
    return {
        "sessions": len(sessions),
        "triggered": len(trades),
        "target": sum(1 for x in trades if x["outcome"] == "target"),
        "stop": sum(1 for x in trades if x["outcome"] == "stop"),
        "close": sum(1 for x in trades if x["outcome"] == "close"),
        "green": sum(1 for x in trades if x["R"] > 0),
        "avg_R": round(statistics.mean(x["R"] for x in trades), 3) if trades else None,
        "rule": rule,
        "trades": trades,
    }


# ---------------------------------------------------------------- the plan


def _num(v, what):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise TMError(f"the plan needs a number for {what}, got {v!r}")
    if not x > 0 or math.isinf(x):
        raise TMError(f"the plan's {what} must be a positive price, got {v!r}")
    return x


def load_plan(a, now_utc):
    """The plan from --plan (an intraday-exit-planner report) or from the flags, checked and normalized."""
    if a.symbol:
        missing = [f for f in ("entry", "stop", "target", "entry_time") if getattr(a, f) is None]
        if missing:
            raise TMError(
                "with --symbol also give {}".format(
                    ", ".join("--" + m.replace("_", "-") for m in missing)
                )
            )
        raw = {
            "symbol": a.symbol,
            "side": a.side,
            "date": a.date or to_eastern(now_utc).date().isoformat(),
            "entry": a.entry,
            "stop": a.stop,
            "target": a.target,
            "entry_time": a.entry_time,
            "setup": a.setup,
            "opening_range": {"minutes": a.or_minutes},
            "stop_rule": a.stop_rule,
            "interval": "5m",
        }
        src = "flags"
    else:
        a.plan = a.plan or latest_report(a.output_dir, "intraday_exit_plan_")
        if not a.plan or not os.path.exists(a.plan):
            raise TMError(
                "no plan at %s: run intraday-exit-planner first, or pass --symbol --date --entry --stop "
                "--target --entry-time" % (a.plan or a.output_dir)
            )
        try:
            with open(a.plan, encoding="utf-8") as fh:
                raw = json.load(fh)
        except ValueError as e:
            raise TMError(f"{a.plan} is not valid JSON: {e}")
        if not isinstance(raw, dict):
            raise TMError(f"{a.plan} is not a plan")
        src = a.plan
    return normalize_plan(raw, src)


def normalize_plan(raw, src="flags"):
    """A plan dict (intraday-exit-planner report shape) -> the checked plan the time machine runs."""
    sym = str(raw.get("symbol") or "").strip().upper()
    if not re.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", sym):
        raise TMError("the plan needs a ticker symbol, got {!r}".format(raw.get("symbol")))
    side = str(raw.get("side") or "buy").lower()
    if side not in ("buy", "sell"):
        raise TMError("side must be buy or sell, got {!r}".format(raw.get("side")))
    interval = str(raw.get("interval") or "5m")
    if interval != "5m":
        raise TMError(
            f"5-minute bars only (the plan says {interval}): Yahoo keeps 60 days of 5-min bars but only about "
            "7 days of 1-min bars, too few sessions for a fair replay pool"
        )
    try:
        date = datetime.date.fromisoformat(str(raw.get("date") or "")).isoformat()
    except ValueError:
        raise TMError("the plan needs a date like 2026-10-19, got {!r}".format(raw.get("date")))
    entry, stop, target = (_num(raw.get(k), k) for k in ("entry", "stop", "target"))
    long = side == "buy"
    if long and not stop < entry < target:
        raise TMError(
            f"a buy needs stop < entry < target (got stop {stop}, entry {entry}, target {target})"
        )
    if not long and not target < entry < stop:
        raise TMError(
            f"a sell needs target < entry < stop (got target {target}, entry {entry}, stop {stop})"
        )
    k = None
    if raw.get("entry_time"):
        close_min = parse_clock(raw["entry_time"], "entry_time")
        if (close_min - OPEN_MIN) % 5:
            raise TMError(
                "entry_time {} is not on the 5-minute grid (use the bar's close, e.g. 10:15 AM)".format(
                    raw["entry_time"]
                )
            )
        k = (close_min - OPEN_MIN) // 5 - 1
    if raw.get("entry_bar") is not None:
        try:
            kb = int(raw["entry_bar"])
        except (TypeError, ValueError):
            raise TMError("entry_bar must be a bar number, got {!r}".format(raw["entry_bar"]))
        if k is not None and kb != k:
            raise TMError(
                "the plan disagrees with itself: entry_bar {:d} but entry_time {} is bar {:d}".format(
                    kb, raw["entry_time"], k
                )
            )
        k = kb
    if k is None:
        raise TMError(
            "the plan needs entry_time (the entry bar's close, e.g. 10:15 AM) or entry_bar"
        )
    if not 0 <= k <= SESSION_BARS - 2:
        raise TMError(
            "the entry must close between 9:35 AM and 3:55 PM to leave bars to replay "
            f"(got {clock12(OPEN_MIN + 5 * (k + 1))})"
        )
    orng = raw.get("opening_range") or {}
    or_min = orng.get("minutes", 15) if isinstance(orng, dict) else 15
    try:
        or_min = int(or_min)
    except (TypeError, ValueError):
        raise TMError("opening_range.minutes must be a number")
    if or_min < 5 or or_min % 5 or or_min >= 390:
        raise TMError(f"opening_range.minutes must be a multiple of 5 (got {or_min})")
    risk = (entry - stop) if long else (stop - entry)
    return {
        "symbol": sym,
        "side": side,
        "date": date,
        "setup": str(raw.get("setup") or "orb"),
        "entry": entry,
        "entry_time": clock12(OPEN_MIN + 5 * (k + 1)),
        "entry_bar": k,
        "stop": stop,
        "target": target,
        "risk_per_share": round(risk, 2),
        "target_r": round(((target - entry) if long else (entry - target)) / risk, 2),
        "opening_range": dict(orng, minutes=or_min)
        if isinstance(orng, dict)
        else {"minutes": or_min},
        "stop_rule": str(raw.get("stop_rule") or "auto"),
        "interval": "5m",
        "flat_by": raw.get("flat_by"),
        "from": src,
    }


def resolve_rule(plan, entry_day):
    """The rule the history replay uses: orb, the plan's opening range, its stop rule
    (or_mid, or_low / or_high, or 'pct' = the plan's stop distance as a percent of
    the entry), and the plan's target R. 'auto' works the stop rule out from the
    plan day's own opening range. None when the setup is not orb."""
    if plan["setup"].lower() != "orb":
        return None
    long = plan["side"] == "buy"
    n = plan["opening_range"]["minutes"] // 5
    rule = {
        "setup": "orb",
        "or_minutes": plan["opening_range"]["minutes"],
        "stop_rule": plan["stop_rule"],
        "target_r": plan["target_r"],
        "stop_pct": round(100.0 * plan["risk_per_share"] / plan["entry"], 4),
    }
    far = "or_low" if long else "or_high"
    if rule["stop_rule"] == "auto":
        rule["stop_rule"] = "pct"
        if all(i in entry_day for i in range(n)):
            oh, ol = opening_range(entry_day, n)
            if abs(cents_away((oh + ol) / 2, long) - plan["stop"]) < 0.005:
                rule["stop_rule"] = "or_mid"
            elif abs(cents_away(ol if long else oh, long) - plan["stop"]) < 0.005:
                rule["stop_rule"] = far
    elif rule["stop_rule"] in ("or_low", "or_high") and rule["stop_rule"] != far:
        rule["stop_rule"] = "pct"
    elif rule["stop_rule"] not in ("or_mid", far):
        rule["stop_rule"] = "pct"
    if rule["stop_rule"] != "pct":
        del rule["stop_pct"]
    return rule


# ---------------------------------------------------------------- the run


def _until12(mc):
    t = mc.get("until") or "16:00"
    return clock12(int(t[:2]) * 60 + int(t[3:]))


def lean(mc):
    """(gap, share, break_even): the target's share of the replays that hit one side,
    minus the share that breaks even at the target's R. None when nothing hit a side."""
    pt, ps = mc["p_target"], mc["p_stop"]
    if pt + ps <= 0:
        return None
    r = mc.get("r_at_target") or 1.0
    share, even = pt / (pt + ps), 1.0 / (1.0 + r)
    return share - even, share, even


def verdict(mc):
    """One line from the numbers, see the docstring for the thresholds."""
    pt, ps = mc["p_target"], mc["p_stop"]
    lv = lean(mc)
    if lv is None:
        return f"No replay reached the target or the stop by {_until12(mc)}: the price at {_until12(mc)} decides every one."
    d, share, even = lv
    r = mc.get("r_at_target") or 1.0
    one_r = abs(r - 1.0) < 0.005
    if abs(d) < COIN_FLIP:
        head = "Close to a coin flip" if one_r else "Close to break-even"
    elif abs(d) < STRONG:
        head = "Leans toward the target" if d > 0 else "Leans toward the stop"
    else:
        head = "Strongly toward the target" if d > 0 else "Strongly toward the stop"
    odds = f"target first {100 * pt:.1f} % vs stop first {100 * ps:.1f} %"
    if one_r:
        return f"{head}: {odds}."
    return (
        f"{head}: at {round(r, 2):g}R the target has to come first in {100 * even:.0f} % of the replays that hit one side; "
        f"it did in {100 * share:.0f} % ({odds})."
    )


def verdict_notes(mc):
    """The lines printed right below the verdict, so nothing reads as one-sided."""
    notes = []
    pn = mc.get("p_neither", 0)
    if pn > MANY_NEITHER and lean(mc) is not None:
        notes.append(
            f"{100 * pn:.1f} % of the replays hit neither by {_until12(mc)}; the price at {_until12(mc)} decides those."
        )
    lv = lean(mc)
    avg = mc.get("avg_R")
    if lv and abs(lv[0]) >= COIN_FLIP and avg is not None and avg != 0 and (avg > 0) != (lv[0] > 0):
        notes.append(
            f"Average R is {avg:+.3f} all the same: the replays that hit neither pull it the other way."
        )
    return notes


def time_machine(text, plan, now_utc, replays=10000, seed=19, window=2, until=None, source="yahoo"):
    """Chart JSON text + a normalized plan -> the timemachine.json document."""
    if not 1 <= replays <= 1000000:
        raise TMError("--replays must be between 1 and 1,000,000")
    if not 0 <= window <= 10:
        raise TMError("--window must be between 0 and 10 bars")
    sym = plan["symbol"]
    result = chart_result(text, sym)
    meta, bars, dropped = parse_bars(result, now_utc)
    msym = str(meta.get("symbol") or "").upper()
    if msym and msym != sym.replace(".", "-"):
        raise TMError(f"the data is for {msym} but the plan is for {sym}")
    gran = meta.get("dataGranularity")
    if gran and gran != "5m":
        raise TMError(f"the data has {gran} bars; the time machine needs 5-minute bars")
    if not bars:
        raise TMError(f"no complete 5-minute bars for {sym} in the data")
    k = plan["entry_bar"]
    close_min = nyse_close_minute(plan["date"])
    early = close_min < CLOSE_MIN
    end_min = close_min
    until_min = end_min if until is None else parse_clock(until, "--until")
    if (until_min - OPEN_MIN) % 5 or until_min > end_min:
        raise TMError(
            "--until must be on the 5-minute grid and no later than {}{}".format(
                clock12(end_min), " (an early close)" if early else ""
            )
        )
    last = (until_min - OPEN_MIN) // 5 - 1
    if last <= k:
        raise TMError(
            "--until {} leaves nothing to replay after the {} entry".format(
                clock12(until_min), plan["entry_time"]
            )
        )
    days = split_sessions(bars)
    entry_day = days.get(plan["date"], {})
    if k not in entry_day:
        reason = (
            "no bars for that day"
            if not entry_day
            else "the data stops at the {} bar".format(entry_day[max(entry_day)]["start"])
        )
        raise TMError(
            "the entry is not in the data: no complete {} bar (closing {}) on {} for {} ({})".format(
                clock24(OPEN_MIN + 5 * k), plan["entry_time"], plan["date"], sym, reason
            )
        )
    eb = entry_day[k]
    warn = []
    if not eb["l"] - 0.01 <= plan["entry"] <= eb["h"] + 0.01:
        warn.append(
            "the plan's entry {:.2f} is outside that bar's range {:.2f} to {:.2f}".format(
                plan["entry"], eb["l"], eb["h"]
            )
        )
    sessions, short = full_sessions(days, plan["date"])
    if len(sessions) < MIN_SESSIONS:
        raise TMError(
            "only {:d} full session(s) of {} before {} in the data; the time machine needs at least {:d}".format(
                len(sessions), sym, plan["date"], MIN_SESSIONS
            )
        )
    pool = build_pool(sessions)
    mc = simulate(
        pool,
        plan["entry"],
        plan["stop"],
        plan["target"],
        k,
        last,
        replays,
        seed,
        window,
        plan["side"],
    )
    mc = dict(
        mc,
        until=clock24(until_min),
        pool_sessions=len(sessions),
        pool_from=sessions[0][0],
        pool_to=sessions[-1][0],
        band_times=[clock24(OPEN_MIN + 5 * (j + 1)) for j in range(k, last + 1)],
    )
    rule = resolve_rule(plan, entry_day)
    plan_out = {kk: v for kk, v in plan.items() if v is not None}
    if rule:
        plan_out["stop_rule"] = rule["stop_rule"]
        history = history_replay(sessions, rule, last, plan["side"])
    else:
        history = {
            "sessions": len(sessions),
            "triggered": 0,
            "rule": None,
            "trades": [],
            "note": "skipped: the history replay knows the opening-range breakout (orb) only, "
            "this plan's setup is {!r}".format(plan["setup"]),
        }
    last_bar = bars[-1]
    return {
        "created_by": "intraday-time-machine",
        "created_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "data": {
            "symbol": msym or sym,
            "interval": "5m",
            "range": "60d",
            "last_bar": "{} {} ET".format(last_bar["date"], last_bar["start"]),
            "dropped": dropped,
            "short_sessions_left_out": short,
        },
        "plan": plan_out,
        "mc": mc,
        "history": history,
        "verdict": verdict(mc),
        "verdict_notes": verdict_notes(mc),
        "warnings": warn,
        "note": (
            f"A simulation built from {sym}'s own last {len(sessions):d} full sessions. It is not a prediction: earnings, news and halts can do things those sessions never did. Same seed, same numbers."
        ),
    }


# ---------------------------------------------------------------- output


def pc(x):
    return "%.1f %%" % (100.0 * x)


def report(doc):
    p, m, h = doc["plan"], doc["mc"], doc["history"]
    long = p["side"] == "buy"
    until = clock12(int(m["until"][:2]) * 60 + int(m["until"][3:]))
    wd = WEEKDAYS[datetime.date.fromisoformat(p["date"]).weekday()]
    r = p["target_r"]
    lines = [
        (
            "{} {}, {} {}: entry {:.2f} at {} (bar {:d}), stop {:.2f}, target {:.2f} ({}R, risk {:.2f} a share).".format(
                p["symbol"],
                p["side"],
                wd,
                p["date"],
                p["entry"],
                p["entry_time"],
                p["entry_bar"],
                p["stop"],
                p["target"],
                f"{r:g}",
                p["risk_per_share"],
            )
        ),
        (
            "{} replays of the rest of the session, {} to {} ({:d} five-minute bars), seed {:d}.".format(
                "{:,}".format(m["replays"]), p["entry_time"], until, m["bars_left"], m["seed"]
            )
        ),
        (
            "Each bar is drawn whole from {}'s own 5-min bars at the same time of day (+-{:d} bars) over its last {:d} full sessions ({} to {}).".format(
                p["symbol"], m["window"], m["pool_sessions"], m["pool_from"], m["pool_to"]
            )
        ),
        "",
        "  target first   {}".format(pc(m["p_target"])),
        "  stop first     {}".format(pc(m["p_stop"])),
        ("  neither        {:<8} still open at {}".format(pc(m["p_neither"]), until)),
        (
            "  green          {:<8} target first, or {} the entry at {}".format(
                pc(m["p_green"]), "above" if long else "below", until
            )
        ),
        "",
        "  Price at {}: median {:.2f}, 90 % of replays between {:.2f} and {:.2f}.".format(
            until, m["median_close"], m["p5_close"], m["p95_close"]
        ),
        "  Average R: {:+.3f} (R = the {:.2f} risk: {}R at the target, -1R at the stop).".format(
            m["avg_R"],
            p["risk_per_share"],
            ("+{:g}".format(m["r_at_target"])),
        ),
        "",
    ]
    if h.get("rule"):
        ru = h["rule"]
        stop_words = {
            "or_mid": "opening-range midpoint",
            "or_low": "opening-range low",
            "or_high": "opening-range high",
        }.get(ru["stop_rule"], "{:.2f} % from the entry".format(ru.get("stop_pct", 0)))
        if h["triggered"]:
            lines.append(
                "History: the same rule ({:d}-min opening range, stop at the {}, {:g}R target) on each of "
                "those {:d} real sessions fired {:d} times: {:d} target, {:d} stop, {:d} neither. Average R {:+.3f}.".format(
                    ru["or_minutes"],
                    stop_words,
                    ru["target_r"],
                    h["sessions"],
                    h["triggered"],
                    h["target"],
                    h["stop"],
                    h["close"],
                    h["avg_R"],
                )
            )
        else:
            lines.append(
                "History: the same rule never fired in those {:d} sessions.".format(h["sessions"])
            )
    else:
        lines.append("History: " + h.get("note", "skipped."))
    lines += ["", doc["verdict"]] + list(doc.get("verdict_notes") or []) + [""]
    for w in doc.get("warnings") or []:
        lines.append("Note: " + w + ".")
    if doc["data"]["short_sessions_left_out"]:
        lines.append(
            "Left out {:d} short session(s) (half days or gaps): {}.".format(
                len(doc["data"]["short_sessions_left_out"]),
                ", ".join(x["date"] for x in doc["data"]["short_sessions_left_out"]),
            )
        )
    lines.append(doc["note"] + (" Repeat this run with --seed {:d}.".format(m["seed"])))
    return lines


def render_chart(doc, height=17):
    """ASCII fan chart of the bands: one column per 5-min bar."""
    p, m = doc["plan"], doc["mc"]
    bands, times = m["bands"], m["band_times"]
    lo = min([b[0] for b in bands] + [p["stop"], p["target"]])
    hi = max([b[4] for b in bands] + [p["stop"], p["target"]])
    pad = (hi - lo) * 0.04 or 0.01
    lo, hi = lo - pad, hi + pad
    step = (hi - lo) / (height - 1)

    def row(price):
        return max(0, min(height - 1, int(round((hi - price) / step))))

    grid = [[" "] * len(bands) for _ in range(height)]
    for j, b in enumerate(bands):
        r5, r25, r50, r75, r95 = [row(x) for x in b]
        for r in range(r95, r5 + 1):
            grid[r][j] = "."
        for r in range(r75, r25 + 1):
            grid[r][j] = ":"
        grid[r50][j] = "*"
    marks = {row(p["target"]): "target", row(p["stop"]): "stop"}
    if row(p["entry"]) not in marks:
        marks[row(p["entry"])] = "entry"
    for r in (row(p["target"]), row(p["stop"])):
        grid[r] = ["-" if ch == " " else ch for ch in grid[r]]
    out = [
        (
            "{} {}, {} replay paths from the {} entry (seed {:d})".format(
                p["symbol"],
                p["date"],
                "{:,}".format(m.get("band_paths", BAND_PATHS)),
                p["entry_time"],
                m["seed"],
            )
        )
    ]
    for r in range(height):
        label = marks.get(r)
        price = {"target": p["target"], "stop": p["stop"], "entry": p["entry"]}.get(
            label, hi - r * step
        )
        left = (f"{price:9.2f} |") if (label or r in (0, height - 1)) else "          |"
        out.append(left + "".join(grid[r]) + ("  " + label if label else ""))
    axis = [" "] * len(bands)
    for j in sorted({0, len(bands) // 2, len(bands) - 1}):
        t = times[j]
        hh, mm = int(t[:2]), t[3:]
        lab = f"{hh % 12 or 12:d}:{mm}"
        s = max(0, min(j, len(bands) - len(lab)))
        axis[s : s + len(lab)] = list(lab)
    out.append("          +" + "-" * len(bands))
    out.append("           " + "".join(axis))
    out.append("* median   : middle half of the paths   . 90 % of the paths   - stop and target")
    return out


# ---------------------------------------------------------------- commands


def _write(path, doc):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")


def latest_report(output_dir, prefix):
    """The newest <output_dir>/<prefix>*.json by modification time, or None."""
    paths = [p for p in glob.glob(os.path.join(output_dir, prefix + "*.json")) if os.path.isfile(p)]
    return max(paths, key=os.path.getmtime) if paths else None


def write_report(output_dir, doc):
    """reports/intraday_timemachine_<TICKER>_<date>.json + .md. Returns (json_path, md_path)."""
    plan = doc["plan"]
    stem = "intraday_timemachine_{}_{}".format(plan["symbol"].replace(".", "-"), plan["date"])
    json_path = os.path.join(output_dir, stem + ".json")
    md_path = os.path.join(output_dir, stem + ".md")
    _write(json_path, doc)
    lines = (
        ["# Intraday Time Machine: {} {}".format(plan["symbol"], plan["date"]), "", "```text"]
        + report(doc)
        + [
            "",
            "\n".join(render_chart(doc)),
            "```",
            "",
            "*A simulation built from the stock's own recent bars, not a prediction.*",
        ]
    )
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return json_path, md_path


def compute(a):
    now = parse_now(a.now)
    plan = load_plan(a, now)
    if a.offline:
        text, source = read_offline(a.offline, plan["symbol"]), "offline"
    else:
        text, source = fetch_chart(plan["symbol"]), "yahoo"
    return time_machine(text, plan, now, a.replays, a.seed, a.window, a.until, source)


def cmd_run(a):
    doc = compute(a)
    written = None
    if not a.no_write:
        written = write_report(a.output_dir, doc)
    if a.json:
        slim = dict(doc, mc={k: v for k, v in doc["mc"].items() if k != "sample_paths"})
        print(json.dumps(slim, indent=2))
    else:
        print("\n".join(report(doc)))
        if written:
            print("Wrote {} and {}.".format(*written))
        print(
            "Next: position-sizer --intraday-plan sizes it to your budget and your max loss per trade."
        )
    return 0


def cmd_chart(a):
    if a.from_file == "latest":
        a.from_file = latest_report(a.output_dir, "intraday_timemachine_")
        if not a.from_file:
            raise TMError(
                f"no intraday_timemachine_*.json in {a.output_dir}: run intraday_time_machine.py run first"
            )
    if a.from_file:
        if not os.path.exists(a.from_file):
            raise TMError(f"no {a.from_file}: run intraday_time_machine.py run first")
        try:
            with open(a.from_file, encoding="utf-8") as fh:
                doc = json.load(fh)
            doc["mc"]["bands"]
        except (ValueError, KeyError, TypeError):
            raise TMError(f"{a.from_file} is not a time machine result")
    else:
        doc = compute(a)
    print("\n".join(render_chart(doc)))
    print("\n".join([doc.get("verdict", "")] + list(doc.get("verdict_notes") or [])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="intraday-time-machine: replay a planned day trade.")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument(
            "--plan",
            help="exit plan report (default: the newest reports/intraday_exit_plan_*.json)",
        )
        p.add_argument(
            "--output-dir", default=DEFAULT_OUTPUT_DIR, help="reports folder (default reports/)"
        )
        p.add_argument("--symbol", help="or give the plan as flags: ticker")
        p.add_argument("--side", default="buy", choices=["buy", "sell"])
        p.add_argument("--date", help="the plan's day, YYYY-MM-DD (default today, New York)")
        p.add_argument("--entry", type=float)
        p.add_argument("--stop", type=float)
        p.add_argument("--target", type=float)
        p.add_argument("--entry-time", help='the entry bar\'s close, e.g. "10:15 AM"')
        p.add_argument("--setup", default="orb")
        p.add_argument("--or-minutes", type=int, default=15)
        p.add_argument(
            "--stop-rule", default="auto", choices=["auto", "or_mid", "or_low", "or_high", "pct"]
        )
        p.add_argument("--replays", type=int, default=10000)
        p.add_argument("--seed", type=int, default=19)
        p.add_argument(
            "--window", type=int, default=2, help="draw from the same time of day +- this many bars"
        )
        p.add_argument("--until", help="end each replay at this time (default 16:00, the close)")
        p.add_argument(
            "--offline",
            metavar="FILE",
            help="a saved Yahoo chart JSON (.json or .json.gz), no network",
        )
        p.add_argument(
            "--now", help='pretend it is this time ("2026-10-19 10:15" New York, or ISO with Z)'
        )

    p = sub.add_parser("run", help="replay the plan: 10,000 simulated sessions plus the history")
    common(p)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-write", action="store_true", help="do not write the report")
    p = sub.add_parser("chart", help="ASCII fan chart of the replays")
    common(p)
    p.add_argument(
        "--from",
        dest="from_file",
        nargs="?",
        const="latest",
        metavar="PATH",
        help="draw a saved result instead of running again (no PATH: the newest report)",
    )
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"run": cmd_run, "chart": cmd_chart}[a.cmd](a)
    except CalendarMissing as e:
        print(f"intraday_time_machine.py: {e}", file=sys.stderr)
        return 2
    except TMError as e:
        print(f"intraday_time_machine.py: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

# Intraday Scanner Rules

## The universe

`universe` downloads `nasdaqlisted.txt` and `otherlisted.txt` from nasdaqtrader.com/dynamic/SymDir and keeps a row when, in this order:

1. It is not a test issue, not an ETF, not NextShares.
2. It is a plain ticker: 1 to 5 letters, or 1 to 4 letters plus one class letter after a dot (BRK.B). A `$` preferred (ABR$D) is out, and so is a `.U`, `.W` or `.R` suffix (units, warrants, rights).
3. Out, whatever else the name says: warrants, SPAC units and rights ("Units, each consisting of", "Rights to receive"), notes, ETNs, debentures, a % coupon, and "Depositary Shares" that are not American or Global (those carry a preferred).
4. In: the name calls it common stock, common shares or units, ordinary shares, shares of beneficial interest, ADS / ADR / American or Global depositary shares, or partnership or trust units.
5. Out: the name still says unit, right, bond, preferred or preference.
6. In: everything else (plain names like "AMETEK, Inc.").

On the 2026-10-19 files this keeps 5,943 symbols (mostly common stock, plus ADRs, closed-end funds and partnership units).

## The daily scan (before the open)

Yahoo's spark endpoint returns closes for 20 symbols a request, so about 5,900 symbols take about 300 requests (about 2.5 minutes with the polite 0.3 s pause). Liquidity comes from the spark meta: last price at least `--min-price` and last session's volume at least `--min-volume`. Run it before the open or after the close: during the session the volume is the day's so far, and today's daily bar is left out until 4:00 PM.

The setups use daily closes only (spark has no highs or lows):

| setup | the rule on closes |
| --- | --- |
| `breakout_20d` | the last close is above every close of the 20 sessions before it |
| `bull_flag` | up more than 10% over the 10 sessions before the last 5, then the last 5 closes inside a 5% range |
| `reclaim_ma20` | the close before was under its 20-day average, the last close is above it |
| `oversold` | RSI 14 (Wilder) under 30 |
| `oversold_bounce` | RSI 14 was under 30 yesterday and today closed up |

A closing-high breakout fires more often than an intraday-high one. Hits are listed most traded first (price times volume).

## The opening-range breakout scan (during the session)

The opening range is the first `--or-minutes` (15) of the session: the 9:30, 9:35 and 9:40 five-minute bars. A hit is the first completed 5-minute bar to CLOSE above the range high, at that bar's close time.

1. **Stage 1, every symbol.** Spark closes of today's 5-minute bars, 20 a request. A chart goes on only if a completed bar after the range closed at or above the highest close of the range. That is a necessary condition (the range high is at least every range close), so no breakout is lost.
2. **Stage 2, each candidate.** The v8 chart with real highs and lows, one request each. Range high = the highest high of the range bars, range low = the lowest low. On a strong morning most charts are candidates, so stage 2 checks at most `--max-confirm` (200) of them, the most traded first (price times volume so far), and prints PARTIAL with the count it skipped. `--max-confirm 0` checks them all.

Timing (Tuesday 2026-10-20, a strong morning): 100 liquid names took 35 seconds. The whole universe took about 4 minutes. For a fast answer, scan the daily watchlist or a list of names (`--watchlist`, `--symbols`).

## Bar rules

- A chart is usable only when every 5-minute bar from 9:30 to the cutoff is there. A missing bar means a halt or a thin stock.
- Null closes are dropped. A bar off the 5-minute grid (the live tick, like 10:58:07) is dropped.
- A bar counts only once it is complete (start + 5 minutes <= the clock).
- Before 9:50 AM, on a weekend or NYSE holiday, after the close, or after `--until` (an expired setup) it prints one plain line and writes nothing.
- Holidays and early closes come from the shared XNYS calendar (`scripts/_market_calendar.py`).

## Data and limits

- Yahoo's chart and spark endpoints are free, unofficial and can lag. query2 first, query1 on a 429 or 5xx, one retry after a 5-second wait on a 429.
- Partial results are reported as partial: "Fetched 4,980 of 5,259 charts (279 failed or had no data)".
- Yahoo keeps only a few days of 5-minute history. Replay an older day with `--offline`.

# Intraday Entry Rules

## Setups (longs only)

- **Opening range (`orb`).** The high and low of the first `--or-minutes` (15): the 9:30, 9:35 and 9:40 five-minute bars, or fifteen 1-minute bars. The level to beat is the range high.
- **Level (`level`).** A price you give with `--level`, like a 20-day high from `intraday-scanner`. In `watchlist` mode a hit's `"level"` field is used when `--level` is not given.

## The trigger

- The trigger is the first completed bar after the range that CLOSES above the level. A wick above is not a trigger. A close exactly at the level is not above it.
- The time is that bar's close time (the 10:10 bar closes at 10:15 AM). The price is its close, to the cent.
- One trigger per setup per day. Later closes do not reset it.

## Closed bars only

- A bar is closed when the clock passes its start plus the interval (5 or 1 minutes) and Yahoo has caught up to that moment (`watch` waits up to a minute for the data).
- Yahoo's live tick (like 10:49:45) is never a bar. Only bars on the interval grid count.
- Without `--now`, an offline file is read as of its own time (`meta.regularMarketTime`).

## Volume (optional)

`--min-volume-x 1.5` also needs the trigger bar's volume at 1.5 times the average volume of the opening-range bars. The 9:30 bar holds the opening auction, so 1.0 is already strict.

## The entry window

- No entries before `--no-entries-before` (09:45) or after `--no-entries-after` (15:30), New York time.
- On an early-close day the cutoff moves up with the close: 15:30 (30 minutes before a 16:00 close) becomes 12:30 before a 1:00 p.m. close. A cutoff already before the early close stays.
- Holidays and early closes come from the shared XNYS calendar (`scripts/_market_calendar.py`).

## Statuses

| status | meaning |
| --- | --- |
| `triggered` | a closed bar closed above the level inside the entry window |
| `waiting` | not open yet, range still forming, or no close above the level yet (the reason says how far) |
| `expired` | no trigger by the cutoff, or the market closed |
| `no-data` | the market is closed today (weekend or NYSE holiday) or Yahoo sent no bars |

## Data

Yahoo's free chart JSON (`/v8/finance/chart/TSLA?range=1d&interval=5m`), unofficial and can lag. query2 first, query1 on HTTP 429 or 5xx, one retry after a pause on a 429. Yahoo keeps about 7 days of 1-minute bars and 60 days of 5-minute bars.

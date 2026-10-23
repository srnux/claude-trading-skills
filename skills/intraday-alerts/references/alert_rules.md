# Alert Rules, Quotes and the NYSE Clock

## Rule types

| type | rings when | rings again |
| --- | --- | --- |
| `above` / `target` | price at or above `price` | after `reset`, or by itself if `"rearm": true` and the price fell back |
| `below` / `stop` | price at or below `price` | same |
| `pct_move` | moved `pct` percent from the previous close (or `ref`), optional `direction` up or down | once per day at most |
| `time` | the New York clock passed `at` ("15:55") on a trading day | once per trading day |
| `opening_bell` | the NYSE is open | once per trading day |

- A rule with `"date"` is watched on that New York date only. `--from-plan` rules carry the plan's date, so yesterday's stop never rings today.
- A `time` rule with `"before_close": true` moves up with an early close by as much as the close moved, so "flat by close" at 15:55 rings at 12:55 before a 1:00 p.m. close.
- `add --from-plan` replaces earlier plan rules for the same ticker and re-arms them.

## Quotes

- `yahoo` (default): `query2.finance.yahoo.com/v8/finance/chart/<TICKER>`, an unofficial free JSON endpoint, one request per ticker, half a second apart. On a 429 it waits and tries once more. On a 429 or a 5xx after that it tries `query1`.
- `stooq`: `stooq.com/q/l/?s=tsla.us&f=sd2t2ohlcv&h&e=csv`, Stooq's free CSV. It answered 404 on 2026-10-13. The parser stays for when it is back.
- `--offline DIR` reads `DIR/<source>-<TICKER>.json|csv` (or `.json.gz`) instead of the network.
- Free quotes are unofficial, delayed and can lag. They are fine for alerts and for checking a size, not for timing an order. Each price in `state/intraday/prices.json` keeps its quote time.
- If both sources are down, read the price from the broker (`portfolio-manager`) and write it into `state/intraday/prices.json` as `{"as_of": "...Z", "prices": {"TSLA": 366.48}}`.

## The NYSE clock

- Regular session 9:30 a.m. to 4:00 p.m. New York time, closed on weekends and NYSE holidays.
- Holidays and early closes come from the repository's shared XNYS calendar (`scripts/_market_calendar.py`, pandas-market-calendars 5.2.2). There is no hard-coded year list.
- Daylight saving time is worked out in the tool and never uses the computer's own time zone.
- Without the calendar dependency every command exits 2 with a message pointing at `requirements.txt`.

# Stop and Target Rules

## Stops (longs only)

| stop | where it goes |
| --- | --- |
| `or-mid` | the opening-range midpoint (the default for an opening-range breakout) |
| `or-low` | the opening-range low: wider, so fewer shares for the same max loss |
| `price:X` | the user's price |
| `pct:X` | X percent under the entry |
| `atr:K` | K times the 14-bar ATR under the entry, on the session's bars up to the entry bar. With fewer than 14 bars by then it averages all of them and says so. At least 3 closed bars are needed |

A level setup has no opening range to lean on, so it needs a stop the user names.

## Targets

| target | where it goes |
| --- | --- |
| `2R` (default) | entry + 2 x risk |
| `1R`, `1.5R`, ... | entry + R x risk |
| `price:X` | the user's price |

## Rounding

- The stop rounds AWAY from the entry to the cent (down, for a long).
- Risk = entry minus stop.
- The target rounds half up to the cent. All money math is Decimal.

## Refusals (with the reason)

- A stop at or above the entry.
- A target at or below the entry.
- A risk under 0.05% of the price: too tight to survive the spread, normal wiggle would stop the trade out.
- An entry report that has not triggered, unless `--entry PRICE` plans ahead.
- A short: the intraday plans are longs only.
- An entry at or after the flat-by time: there is no time left to hold it.

## Flat by

- 15:55 New York time by default: out by then, win or lose, no overnight hold.
- On an early-close day the default moves up with the close (12:55 before a 1:00 p.m. close). Early closes come from the shared XNYS calendar (`scripts/_market_calendar.py`).
- `--flat-by HH:MM` sets an exact time. One at or after that day's close is refused.

## Reward:risk floor

`--min-reward-risk` (default 1.0) only adds a warning here. `position-sizer --intraday-plan` refuses to size a plan under its own `--min-reward-risk` floor.

# Replay Method

## 1. The pool

Keep only FULL sessions before the plan's date: all 78 five-minute bars, 9:30 to 4:00 New York time. Half days, gaps and today are left out. Every bar becomes four ratios to the bar before it: open, high, low and close over the previous close. At least 20 full sessions are required.

## 2. One replay

Start at the entry price. For each bar left in the day, pick a past bar from the same time of day (plus or minus `--window`, 2 bars) at random, and scale it to the current price. Bar by bar, check the stop first, then the target. A bar that touches both counts as the stop (the conservative call).

## 3. Outcomes of 10,000 replays

| outcome | meaning |
| --- | --- |
| target first | the target was touched before the stop |
| stop first | the stop was touched before the target |
| neither | still open at `--until` (default 4:00 PM, or the early close on an NYSE half day) |
| green | target first, or above the entry at `--until` |

R is the target's R at the target, -1 at the stop, and otherwise the distance from the entry at `--until` divided by the risk. A gap through the stop still counts as -1R here. A real fill can be worse.

The price at `--until`: median and the 5th to 95th percentile of all replays. The fan chart uses a second run of 2,000 paths with the same seed. The histogram has 24 bins between the 1st and 99th percentile.

## 4. The history

The plan's own rule (an opening-range breakout with the same opening range, stop rule and target R) runs again on every past full session: first close beyond the range = entry, same stop-first rule. That is what really happened, not a simulation. The history replay knows the opening-range breakout only. For a level setup it is skipped and says so.

## 5. The verdict

Look only at the replays that hit one side and ask how often the target came first, target / (target + stop). A bigger target needs to win less often to break even: 1 / (1 + R). That is 50% at 1R, 33% at 2R, 25% at 3R. The gap in percentage points:

| gap | verdict |
| --- | --- |
| under 5 points | "Close to a coin flip" (1R) / "Close to break-even" (other R) |
| 5 to 15 points | "Leans toward the target" / "Leans toward the stop" |
| 15 points or more | "Strongly toward the target" / "Strongly toward the stop" |

Below the verdict, when it applies: a note when more than 40% of the replays hit neither (the price at `--until` decides those), and the average R when its sign goes against the lean.

## 6. The seed

Draws come from Python's `random.Random(seed)`, seed 19 by default. Same plan, same data, same seed: the same numbers on any machine.

## 7. Refusals (one plain line)

- Fewer than 20 full sessions in the data
- The entry bar is not in the data (wrong date, not closed yet, a future day)
- A plan that makes no sense (a stop above a buy's entry, an entry off the 5-minute grid)
- 1-minute bars: Yahoo keeps only about 7 days of them, too few sessions for a fair pool

A live in-progress bar is never used, and today's bars never enter the pool.

# Attribution

This skill is adapted from `trader-entry/entry.py` and its tests in
[day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill)
(commit 3d0f4ef, "The Trader skill v2") by Jake Schincariol, used under the MIT License below.

Changes for this repository: the skills/<name>/scripts layout and pytest tests,
JSON + Markdown reports in `reports/` and state in `state/intraday/` instead of a
`trader/` folder, the shared XNYS calendar (`scripts/_market_calendar.py`) instead
of hard-coded 2026 and 2027 holidays, CLI flags instead of `trader/config.json`,
handoffs to this repository's position-sizer, pre-trade-discipline-gate and
portfolio-manager, and ruff formatting.

---

MIT License

Copyright (c) 2026 Jake Schincariol

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

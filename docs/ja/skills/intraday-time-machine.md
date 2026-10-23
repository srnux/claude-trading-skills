---
layout: default
title: "Intraday Time Machine"
grand_parent: 日本語
parent: スキルガイド
nav_order: 41
lang_peer: /en/skills/intraday-time-machine/
permalink: /ja/skills/intraday-time-machine/
generated: true
---

# Intraday Time Machine
{: .no_toc }

Replay a planned day trade before risking a dollar. Takes the plan from intraday-exit-planner (entry, stop, target), rebuilds the rest of the session 10,000 times from the stock's own 5-minute bars over the last 60 days, re-runs the same opening-range rule on every past session, and prints the odds of target first, stop first or neither, the price at the close, the average R, the history and one honest verdict. Use when the user says "run the time machine", "replay this trade", "what are the odds", "simulate this trade", "monte carlo", "backtest this setup", "is this a coin flip", or after intraday-exit-planner and before position-sizer.
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/intraday-time-machine.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/intraday-time-machine){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/intraday-time-machine/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/intraday-time-machine/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }

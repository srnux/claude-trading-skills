---
layout: default
title: "Intraday Exit Planner"
grand_parent: 日本語
parent: スキルガイド
nav_order: 39
lang_peer: /en/skills/intraday-exit-planner/
permalink: /ja/skills/intraday-exit-planner/
generated: true
---

# Intraday Exit Planner
{: .no_toc }

Set the stop and the target of a day trade before the entry, so the exit is decided before the money is in. Reads the trigger from intraday-entry-timer (or a price you give), puts the stop at the opening-range midpoint by default (or the range low, a price, a percent, or a multiple of the ATR), sets the target at 2R (or 1R, or a price), adds a flat-by time, and refuses plans that make no sense. Long side only, never places an order. Use when the user asks "where's my stop", "set my stop and target", "plan the exit", "what's my R", "risk reward", or right after intraday-entry-timer triggers.
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/intraday-exit-planner.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/intraday-exit-planner){: .btn .fs-5 .mb-4 .mb-md-0 }

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/intraday-exit-planner/' | relative_url }}) for the full guide.
{: .warning }

---

[English版ガイドを見る]({{ '/en/skills/intraday-exit-planner/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }

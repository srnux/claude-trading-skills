#!/usr/bin/env python3
"""
Uptrend Analyzer - HTML Report

Renders the same analysis as the Markdown report as a self-contained HTML page.
Every value is shown next to what it measures and a rule-based reading of
today's value, so the report can be read without the methodology reference.
"""

import html
import sys

OVERBOUGHT_PCT = 37.0
OVERSOLD_PCT = 9.7
SCALE_MAX_PCT = 50.0

COMPONENT_ORDER = [
    "market_breadth",
    "sector_participation",
    "sector_rotation",
    "momentum",
    "historical_context",
]

COMPONENT_MEANING = {
    "market_breadth": "Share of all stocks in an uptrend, and whether that share is rising.",
    "sector_participation": "How many of the 11 sectors are in uptrends, and how evenly.",
    "sector_rotation": (
        "Which kind of sector leads: cyclical (risk-on), defensive (risk-off) "
        "or commodity (often late cycle)."
    ),
    "momentum": "Whether breadth is improving, and whether that improvement is speeding up.",
    "historical_context": "How today's ratio compares with every day in the data history.",
}

ZONES = [
    ("80-100", "Strong Bull", "Full exposure (100%)"),
    ("60-79", "Bull", "Normal exposure (80-100%)"),
    ("40-59", "Neutral", "Reduced exposure (60-80%)"),
    ("20-39", "Cautious", "Defensive (30-60%)"),
    ("0-19", "Bear", "Capital preservation (0-30%)"),
]


# --- Rule-based readings -------------------------------------------------


def explain_ratio_level(ratio_pct, median_pct) -> str:
    """Interpret the uptrend ratio against Monty's thresholds and the median."""
    if ratio_pct is None:
        return "No data."
    if ratio_pct >= OVERBOUGHT_PCT:
        return (
            "Overbought: most stocks are already in uptrends. Late to chase; pullbacks are likely."
        )
    if ratio_pct <= OVERSOLD_PCT:
        return "Oversold: almost nothing is in an uptrend. Washed out; watch for a turn."
    if median_pct is None:
        return "Normal range, between oversold and overbought."
    side = "above" if ratio_pct >= median_pct else "below"
    return f"Normal range, {side} the historical median of {median_pct}%."


def explain_ratio_vs_ma(ratio_pct, ma_pct) -> str:
    """Compare today's ratio with its 10-day average."""
    if ratio_pct is None or ma_pct is None:
        return "No data."
    if ratio_pct > ma_pct:
        return f"Above its 10-day average ({ma_pct}%): participation is improving."
    if ratio_pct < ma_pct:
        return f"Below its 10-day average ({ma_pct}%): participation is fading."
    return "Equal to its 10-day average: participation is flat."


def explain_composite(score, raw_score, zone) -> str:
    """Explain the composite score and any penalty applied to it."""
    text = f"{score}/100 puts the market in the {zone} zone."
    if raw_score is not None and raw_score != score:
        text += (
            f" Without the active warnings it would be {raw_score}; "
            f"they pulled it down by {abs(raw_score - score):.1f} points."
        )
    return text


def explain_spread(spread_pct) -> str:
    """Interpret the gap between the strongest and weakest sector."""
    if spread_pct is None:
        return "No data."
    if spread_pct > 40:
        return "Very wide gap between best and worst sector: a selective market where sector choice matters."
    if spread_pct > 25:
        return "Moderate gap: leadership is somewhat uneven."
    return "Sectors are moving fairly evenly: broad participation."


def explain_sector_row(status, trend) -> str:
    """Combine a sector's level (status) with its direction (trend)."""
    rising = str(trend).lower() == "up"
    if status == "Overbought":
        if rising:
            return "Strong but stretched; late entries carry pullback risk."
        return "High level but rolling over; a warning sign for a leader."
    if status == "Oversold":
        if rising:
            return "Very weak but starting to recover; early and unconfirmed."
        return "Very weak and still falling; avoid."
    if rising:
        return "Normal level and strengthening."
    return "Normal level but weakening."


def _explain_trend(trend) -> str:
    if trend is None:
        return "No data."
    if str(trend).lower() == "up":
        return "The 10-day average is rising."
    return "The 10-day average is falling."


def _explain_sector_count(count, total) -> str:
    if not total:
        return "No data."
    share = count / total
    if share >= 0.7:
        return "Most sectors take part in the move."
    if share >= 0.45:
        return "About half the sectors take part."
    return "Only a few sectors carry the market."


def _explain_rotation_gap(gap_pct) -> str:
    if gap_pct is None:
        return "No data."
    if gap_pct > 5:
        return "Cyclicals lead defensives: a risk-on tone."
    if gap_pct < -5:
        return "Defensives lead cyclicals: a risk-off tone."
    return "Cyclicals and defensives are roughly level: no clear risk appetite."


def _explain_commodity(commodity, cyclical, defensive) -> str:
    if None in (commodity, cyclical, defensive):
        return "No data."
    if commodity > cyclical and commodity > defensive:
        return "Commodity sectors lead both groups. This often happens late in a cycle."
    return "Commodity sectors are not leading."


def _explain_slope(slope) -> str:
    if slope is None:
        return "No data."
    if slope > 0:
        return "Positive: breadth is rising."
    if slope < 0:
        return "Negative: breadth is falling."
    return "Flat."


def _explain_acceleration(label) -> str:
    mapping = {
        "accelerating": "The rise is speeding up.",
        "decelerating": "The move is slowing down.",
        "steady": "The pace is steady.",
    }
    return mapping.get(str(label).lower(), str(label))


def _explain_percentile(percentile) -> str:
    if percentile is None:
        return "No data."
    if percentile >= 80:
        return f"Higher than {percentile}% of past days: historically strong."
    if percentile <= 20:
        return f"Higher than only {percentile}% of past days: historically weak."
    return f"Higher than {percentile}% of past days: an ordinary reading."


def _explain_recent_avgs(avg_30, avg_90) -> str:
    if avg_30 is None or avg_90 is None:
        return "No data."
    if avg_30 < avg_90:
        return "The last month was weaker than the last quarter."
    if avg_30 > avg_90:
        return "The last month was stronger than the last quarter."
    return "The last month matched the last quarter."


# --- HTML helpers ---------------------------------------------------------


def _e(value) -> str:
    return html.escape("N/A" if value is None else str(value))


def _pct(value) -> str:
    return "N/A" if value is None else f"{value}%"


def _pp(value) -> str:
    if value is None:
        return "N/A"
    return f"{round(value * 100, 1):+.1f} pts"


def _slope(value) -> str:
    return "N/A" if value is None else f"{value:+.4f}"


def _tone(score) -> str:
    if score is None:
        return "na"
    if score >= 60:
        return "good"
    if score >= 40:
        return "mid"
    return "bad"


def _score_bar(score) -> str:
    width = max(0, min(100, score or 0))
    return (
        f'<div class="bar"><span class="fill {_tone(score)}" style="width:{width}%"></span></div>'
    )


def _table(headers, rows) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return (
        f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _explained_table(rows) -> str:
    """rows: (metric, value, what it measures, today) with plain-text cells."""
    cells = [
        (f"<strong>{_e(m)}</strong>", f'<span class="val">{_e(v)}</span>', _e(w), _e(t))
        for m, v, w, t in rows
    ]
    return _table(["Metric", "Value", "What it measures", "Today"], cells)


def _section(title, intro, body) -> str:
    intro_html = f'<p class="intro">{_e(intro)}</p>' if intro else ""
    return f"<section><h2>{_e(title)}</h2>{intro_html}{body}</section>"


def _ratio_scale(ratio_pct, median_pct) -> str:
    """Horizontal scale with oversold / normal / overbought bands and markers."""

    def pos(v):
        return max(0.0, min(100.0, v / SCALE_MAX_PCT * 100))

    markers = ""
    if median_pct is not None:
        markers += (
            f'<span class="tick" style="left:{pos(median_pct):.1f}%" '
            f'title="Historical median"><em>median {_e(median_pct)}%</em></span>'
        )
    if ratio_pct is not None:
        markers += (
            f'<span class="marker" style="left:{pos(ratio_pct):.1f}%">'
            f"<b>today {_e(ratio_pct)}%</b></span>"
        )
    return (
        '<div class="scale">'
        f'<span class="band os" style="width:{pos(OVERSOLD_PCT):.1f}%">Oversold</span>'
        f'<span class="band nm" style="width:{pos(OVERBOUGHT_PCT) - pos(OVERSOLD_PCT):.1f}%">Normal</span>'
        f'<span class="band ob" style="width:{100 - pos(OVERBOUGHT_PCT):.1f}%">Overbought</span>'
        f"{markers}</div>"
        f'<div class="scale-axis"><span>0%</span><span>{OVERSOLD_PCT}%</span>'
        f"<span>{OVERBOUGHT_PCT:.0f}%</span><span>{SCALE_MAX_PCT:.0f}%+</span></div>"
    )


# --- Sections -------------------------------------------------------------


def _how_to_read(breadth, historical) -> str:
    zones = _table(
        ["Score", "Zone", "Exposure guidance"],
        [(_e(r), _e(z), _e(g)) for r, z, g in ZONES],
    )
    return _section(
        "How to read this report",
        None,
        "<p>Everything here is built on one number, the <strong>uptrend ratio</strong>: "
        "the share of about 2,800 liquid US stocks that are in a clean uptrend. A stock counts "
        "only if it is above its 20-day and 200-day averages, its 50-day average is above the "
        "200-day, it is more than 30% above its 52-week low, and it is up over the last 4 weeks.</p>"
        "<p>The ratio rarely uses the full 0-100% range. Below 9.7% is oversold, above 37% is "
        "overbought.</p>"
        + _ratio_scale(breadth.get("ratio_pct"), historical.get("historical_median_pct"))
        + "<p>Five components turn the ratio and its sector breakdown into a "
        "<strong>composite score from 0 to 100</strong> (higher = healthier). The score maps to "
        "a zone:</p>" + zones + '<p class="note">The exposure guidance is this indicator\'s '
        "view alone. The daily exposure decision (exposure-coach) also weighs market breadth "
        "and top risk, so it can be stricter.</p>",
    )


def _overall(composite, historical) -> str:
    score = composite.get("composite_score")
    raw = composite.get("composite_score_raw", score)
    zone = composite.get("zone", "Unknown")
    prox = composite.get("zone_proximity", {}) or {}
    strongest = composite.get("strongest_component", {}) or {}
    weakest = composite.get("weakest_component", {}) or {}
    warnings = composite.get("active_warnings", []) or []
    confidence = historical.get("confidence", {}) or {}

    rows = [
        (
            "Composite score",
            f"{score}/100",
            "Overall breadth health, 0-100. Higher is healthier.",
            explain_composite(score, raw, zone),
        ),
        (
            "Zone",
            composite.get("zone_detail", zone),
            "The band the score falls in (see the zone table above).",
            composite.get("guidance", ""),
        ),
    ]
    if prox.get("at_boundary"):
        rows.append(
            (
                "Zone proximity",
                prox.get("label", ""),
                "How close the score is to the next zone.",
                "Close to a zone boundary: a small move would change the zone.",
            )
        )
    rows.append(
        (
            "Exposure guidance",
            composite.get("exposure_guidance", "N/A"),
            "Suggested share of capital in equities, from this indicator alone.",
            "Treat as an upper bound; the exposure-coach decision is the one to act on.",
        )
    )
    if composite.get("warning_penalty"):
        rows.append(
            (
                "Warning penalty",
                f"{composite.get('warning_penalty')} (raw {raw}/100)",
                "Points deducted for the active warnings listed below.",
                f"{len(warnings)} warning(s) active.",
            )
        )
    rows.extend(
        [
            (
                "Strongest component",
                f"{strongest.get('label', 'N/A')} ({strongest.get('score', 0)}/100)",
                "The part of the score holding it up most.",
                "Where the market looks best right now.",
            ),
            (
                "Weakest component",
                f"{weakest.get('label', 'N/A')} ({weakest.get('score', 0)}/100)",
                "The part of the score dragging it down most.",
                "Where the market looks worst right now.",
            ),
        ]
    )
    dq = composite.get("data_quality", {}) or {}
    if dq:
        rows.append(
            (
                "Data quality",
                dq.get("label", "N/A"),
                "How many of the 5 components had data.",
                "Complete data." if "Complete" in str(dq.get("label")) else "Some data missing.",
            )
        )
    if confidence:
        rows.append(
            (
                "Confidence",
                confidence.get("confidence_level", "N/A"),
                "How much history backs the comparison (sample size, bull and bear periods, recency).",
                f"Sample {confidence.get('sample_label', '')}, regime coverage "
                f"{confidence.get('regime_coverage', '')}.",
            )
        )

    verdict = (
        f'<div class="verdict {_tone(score)}"><div class="big">{_e(score)}<small>/100</small></div>'
        f'<div><div class="zone">{_e(zone)}</div><div>{_e(composite.get("exposure_guidance"))}</div>'
        f'<div class="muted">{_e(composite.get("guidance"))}</div></div></div>'
    )
    return _section("Overall Assessment", None, verdict + _explained_table(rows))


def _warnings(composite) -> str:
    warnings = composite.get("active_warnings", []) or []
    if not warnings:
        return ""
    cards = ""
    for w in warnings:
        actions = "".join(f"<li>{_e(a)}</li>" for a in w.get("actions", []))
        cards += (
            f'<div class="card warn"><h3>{_e(w.get("label"))}</h3>'
            f"<p>{_e(w.get('description'))}</p>"
            f'<p class="muted">What to do:</p><ul>{actions}</ul></div>'
        )
    return _section(
        "Active Warnings",
        "Problems the score alone hides. Each one also lowers the composite score.",
        cards,
    )


def _snapshot(breadth, historical) -> str:
    if not breadth.get("data_available"):
        return _section("Current Market Snapshot", None, "<p>Data unavailable.</p>")
    ratio = breadth.get("ratio_pct")
    rows = [
        (
            "Uptrend ratio",
            _pct(ratio),
            "Share of all stocks in a clean uptrend.",
            explain_ratio_level(ratio, historical.get("historical_median_pct")),
        ),
        (
            "10-day average",
            _pct(breadth.get("ma_10_pct")),
            "The ratio smoothed over 10 days, to filter daily noise.",
            explain_ratio_vs_ma(ratio, breadth.get("ma_10_pct")),
        ),
        (
            "Trend",
            breadth.get("trend"),
            "Direction of the 10-day average.",
            _explain_trend(breadth.get("trend")),
        ),
        (
            "Slope",
            _slope(breadth.get("slope")),
            "Daily change of the 10-day average.",
            _explain_slope(breadth.get("slope")),
        ),
        (
            "Distance to overbought (37%)",
            _pp(breadth.get("distance_from_upper")),
            "How far the ratio is from the overbought line.",
            "Room left before the market looks stretched."
            if (breadth.get("distance_from_upper") or 0) < 0
            else "Already above the overbought line.",
        ),
        (
            "Distance to oversold (9.7%)",
            _pp(breadth.get("distance_from_lower")),
            "How far the ratio is from the oversold line.",
            "Well clear of oversold."
            if (breadth.get("distance_from_lower") or 0) > 0.05
            else "Close to or below oversold.",
        ),
        (
            "Data date",
            breadth.get("date"),
            "Trading day the data is from (US close).",
            "Usually the previous US session.",
        ),
    ]
    return _section("Current Market Snapshot", None, _explained_table(rows))


def _component_scores(composite, components) -> str:
    rows = []
    for i, key in enumerate(COMPONENT_ORDER, 1):
        comp = composite.get("component_scores", {}).get(key, {})
        score = comp.get("score", 0)
        rows.append(
            (
                _e(i),
                f"<strong>{_e(comp.get('label', key))}</strong>",
                _e(f"{comp.get('weight', 0) * 100:.0f}%"),
                f'{_score_bar(score)}<span class="val">{_e(score)}</span>',
                _e(f"{comp.get('weighted_contribution', 0):.1f}"),
                _e(COMPONENT_MEANING.get(key, "")),
                _e(components.get(key, {}).get("signal", "N/A")),
            )
        )
    table = _table(
        ["#", "Component", "Weight", "Score", "Contribution", "What it measures", "Today"],
        rows,
    )
    return _section(
        "Component Scores",
        "Contribution = score x weight. The contributions add up to the raw composite score.",
        table,
    )


def _component_details(components, historical) -> str:
    parts = []

    participation = components.get("sector_participation", {})
    if participation.get("data_available"):
        count = participation.get("uptrend_count", 0)
        total = participation.get("total_sectors", 0)
        ob = ", ".join(participation.get("overbought_sectors", [])) or "none"
        os_ = ", ".join(participation.get("oversold_sectors", [])) or "none"
        parts.append(
            "<h3>Sector participation</h3>"
            + _explained_table(
                [
                    (
                        "Uptrending sectors",
                        f"{count}/{total}",
                        "Sectors whose 10-day average is rising.",
                        _explain_sector_count(count, total),
                    ),
                    (
                        "Spread",
                        f"{participation.get('spread_pct')} pts",
                        "Gap between the strongest and weakest sector's ratio.",
                        explain_spread(participation.get("spread_pct")),
                    ),
                    (
                        "Overbought sectors (>37%)",
                        ob,
                        "Sectors where most stocks are already in uptrends.",
                        "Stretched; avoid chasing." if ob != "none" else "None stretched.",
                    ),
                    (
                        "Oversold sectors (<9.7%)",
                        os_,
                        "Sectors where almost no stocks are in uptrends.",
                        "Washed out; see the heatmap for whether they are turning."
                        if os_ != "none"
                        else "None washed out.",
                    ),
                ]
            )
        )

    rotation = components.get("sector_rotation", {})
    if rotation.get("data_available"):
        cyc = rotation.get("cyclical_avg_pct")
        dfn = rotation.get("defensive_avg_pct")
        com = rotation.get("commodity_avg_pct")
        rows = [
            (
                "Cyclical average",
                _pct(cyc),
                "Tech, consumer cyclical, communication, financials, industrials.",
                "Sectors that lead when investors take risk.",
            ),
            (
                "Defensive average",
                _pct(dfn),
                "Utilities, consumer defensive, healthcare, real estate.",
                "Sectors that lead when investors seek safety.",
            ),
            (
                "Commodity average",
                _pct(com),
                "Energy and basic materials.",
                _explain_commodity(com, cyc, dfn),
            ),
            (
                "Cyclical minus defensive",
                f"{rotation.get('difference_pct')} pts",
                "Positive = cyclicals lead (risk-on); negative = defensives lead.",
                _explain_rotation_gap(rotation.get("difference_pct")),
            ),
        ]
        for label, key in (
            ("Cyclical", "cyclical_divergence"),
            ("Defensive", "defensive_divergence"),
        ):
            div = rotation.get(key, {}) or {}
            if div.get("flagged"):
                dissent = ", ".join(
                    f"{d['sector']} ({d['trend']})" for d in div.get("trend_dissenters", [])
                )
                rows.append(
                    (
                        f"{label} divergence",
                        f"spread {div.get('spread')}",
                        f"Whether {label.lower()} sectors move together.",
                        f"Sectors in this group disagree. Moving against the group: {dissent}."
                        if dissent
                        else "Sectors in this group sit far apart in strength.",
                    )
                )
        parts.append("<h3>Sector rotation</h3>" + _explained_table(rows))

    momentum = components.get("momentum", {})
    if momentum.get("data_available"):
        pos = momentum.get("sector_positive_slope_count", 0)
        tot = momentum.get("sector_total", 0)
        parts.append(
            "<h3>Momentum</h3>"
            + _explained_table(
                [
                    (
                        "Smoothed slope",
                        _slope(momentum.get("slope_smoothed")),
                        "Direction of breadth, smoothed over 3 days.",
                        _explain_slope(momentum.get("slope_smoothed")),
                    ),
                    (
                        "Acceleration",
                        momentum.get("acceleration_label"),
                        "Last 10 days' slope vs the 10 days before.",
                        _explain_acceleration(momentum.get("acceleration_label")),
                    ),
                    (
                        "Sectors with rising breadth",
                        f"{pos}/{tot}",
                        "How many sectors are improving.",
                        _explain_sector_count(pos, tot),
                    ),
                ]
            )
        )

    if historical.get("data_available"):
        parts.append(
            "<h3>Historical context</h3>"
            + _explained_table(
                [
                    (
                        "Percentile rank",
                        f"{historical.get('percentile')}th",
                        "Share of past days with a lower ratio than today.",
                        _explain_percentile(historical.get("percentile")),
                    ),
                    (
                        "Historical median",
                        _pct(historical.get("historical_median_pct")),
                        "The typical ratio over the whole history.",
                        explain_ratio_level(
                            historical.get("current_ratio_pct"),
                            historical.get("historical_median_pct"),
                        ),
                    ),
                    (
                        "Historical range",
                        f"{_pct(historical.get('historical_min_pct'))} - "
                        f"{_pct(historical.get('historical_max_pct'))}",
                        "Lowest and highest ratio seen.",
                        f"History: {historical.get('date_range', 'N/A')}.",
                    ),
                    (
                        "30-day / 90-day average",
                        f"{_pct(historical.get('avg_30d_pct'))} / {_pct(historical.get('avg_90d_pct'))}",
                        "Recent averages, to see the short-term path.",
                        _explain_recent_avgs(
                            historical.get("avg_30d_pct"), historical.get("avg_90d_pct")
                        ),
                    ),
                ]
            )
        )

    if not parts:
        return ""
    return _section(
        "Component Details", "The inputs behind each component, explained.", "".join(parts)
    )


def _heatmap(components) -> str:
    sectors = components.get("sector_participation", {}).get("sector_details", []) or []
    if not sectors:
        return ""
    rows = []
    for i, s in enumerate(sectors, 1):
        ratio = s.get("ratio_pct")
        ma = round(s["ma_10"] * 100, 1) if s.get("ma_10") is not None else None
        count = s.get("count")
        total = s.get("total")
        width = max(0.0, min(100.0, (ratio or 0) / SCALE_MAX_PCT * 100))
        status = s.get("status", "")
        rows.append(
            (
                _e(i),
                f"<strong>{_e(s.get('sector'))}</strong>",
                f'<div class="bar"><span class="fill {status.lower() or "normal"}" '
                f'style="width:{width:.0f}%"></span></div><span class="val">{_e(_pct(ratio))}</span>',
                _e(f"{count}/{total}" if count is not None and total is not None else "N/A"),
                _e(_pct(ma)),
                _e(s.get("trend")),
                _e(status),
                _e(explain_sector_row(status, s.get("trend"))),
            )
        )
    table = _table(
        ["#", "Sector", "Ratio", "Stocks", "10-day avg", "Trend", "Status", "Today"], rows
    )
    return _section(
        "Sector Heatmap",
        "Status is the level (oversold / normal / overbought); trend is the direction of the "
        "10-day average. Read them together.",
        table,
    )


def _actions(composite) -> str:
    items = "".join(f"<li>{_e(a)}</li>" for a in composite.get("actions", []))
    return _section(
        "Recommended Actions",
        f"Standard actions for the {composite.get('zone', 'Unknown')} zone.",
        f"<ul>{items}</ul>",
    )


CSS = """
:root{--bg:#f7f7f5;--surface:#fff;--text:#1d1d1b;--muted:#6b6b66;--border:#e3e2dd;
--good:#2f8f5b;--mid:#c9a227;--bad:#c4472f;--os:#f3d9d2;--nm:#e9efe6;--ob:#f6e6c4;--accent:#2b5cab}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--surface:#1f1f1d;
--text:#ecebe6;--muted:#a3a29b;--border:#34342f;--good:#4fb47c;--mid:#d9b440;--bad:#e06a52;
--os:#4a2a24;--nm:#25311f;--ob:#4a3b1c;--accent:#7aa2e3}}
:root[data-theme="dark"]{--bg:#161615;--surface:#1f1f1d;--text:#ecebe6;--muted:#a3a29b;--border:#34342f;
--good:#4fb47c;--mid:#d9b440;--bad:#e06a52;--os:#4a2a24;--nm:#25311f;--ob:#4a3b1c;--accent:#7aa2e3}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
header h1{margin:0 0 4px;font-size:26px}
.muted,header p{color:var(--muted)}
section{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px;margin:18px 0}
h2{margin:0 0 10px;font-size:19px}h3{margin:18px 0 8px;font-size:16px}
.intro,.note{color:var(--muted);margin-top:0}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th{text-align:left;font-weight:600;color:var(--muted);border-bottom:2px solid var(--border);padding:8px 10px;white-space:nowrap}
td{border-bottom:1px solid var(--border);padding:8px 10px;vertical-align:top}
td:last-child{min-width:220px}
.val{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
.bar{display:inline-block;width:80px;height:8px;background:var(--border);border-radius:4px;margin-right:8px;vertical-align:middle;overflow:hidden}
.fill{display:block;height:100%}
.fill.good{background:var(--good)}.fill.mid{background:var(--mid)}.fill.bad{background:var(--bad)}
.fill.overbought{background:var(--mid)}.fill.normal{background:var(--good)}.fill.oversold{background:var(--bad)}
.verdict{display:flex;gap:20px;align-items:center;padding:14px 16px;border-radius:8px;margin-bottom:14px;border-left:6px solid var(--mid);background:var(--bg)}
.verdict.good{border-color:var(--good)}.verdict.bad{border-color:var(--bad)}
.big{font-size:42px;font-weight:700;line-height:1}.big small{font-size:16px;color:var(--muted)}
.zone{font-size:18px;font-weight:600}
.card{border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin:10px 0}
.card.warn{border-left:5px solid var(--mid)}.card h3{margin-top:0}
.scale{position:relative;display:flex;height:30px;margin:34px 0 4px;border-radius:6px;overflow:visible;font-size:12px}
.band{display:flex;align-items:center;justify-content:center;color:var(--muted)}
.band.os{background:var(--os);border-radius:6px 0 0 6px}.band.nm{background:var(--nm)}.band.ob{background:var(--ob);border-radius:0 6px 6px 0}
.marker,.tick{position:absolute;top:-6px;bottom:-6px;width:3px;background:var(--accent)}
.tick{width:1px;background:var(--muted)}
.marker b,.tick em{position:absolute;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:12px}
.marker b{top:-20px;color:var(--accent)}.tick em{bottom:-20px;color:var(--muted)}
.scale-axis{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin:22px 0 14px}
footer{color:var(--muted);font-size:13px;margin-top:24px}
"""


def generate_html_report(analysis: dict, output_file: str):
    """Write a self-contained HTML report with explanations for every value."""
    composite = analysis.get("composite", {})
    components = analysis.get("components", {})
    metadata = analysis.get("metadata", {})
    breadth = components.get("market_breadth", {})
    historical = components.get("historical_context", {})

    body = (
        _how_to_read(breadth, historical)
        + _overall(composite, historical)
        + _warnings(composite)
        + _snapshot(breadth, historical)
        + _component_scores(composite, components)
        + _component_details(components, historical)
        + _heatmap(components)
        + _actions(composite)
    )
    page = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Uptrend Analysis {_e(breadth.get('date', ''))}</title><style>{CSS}</style></head>"
        "<body><main><header><h1>Uptrend Analyzer Report</h1>"
        f"<p>Generated {_e(metadata.get('generated_at'))} · Data as of {_e(breadth.get('date'))} · "
        "Source: Monty's Uptrend Ratio Dashboard</p></header>"
        f"{body}<footer>For education and information only. Not investment advice. "
        "Past patterns may not predict future outcomes.</footer></main></body></html>\n"
    )

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(page)
    except OSError as e:
        print(f"ERROR: Failed to write HTML report to {output_file}: {e}", file=sys.stderr)
        raise

    print(f"HTML report saved to: {output_file}")

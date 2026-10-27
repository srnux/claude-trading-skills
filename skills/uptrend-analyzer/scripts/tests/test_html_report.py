"""Tests for the HTML report: same data as the Markdown report plus a
'how to read' explanation and a rule-based reading of today's value."""

import pytest
from html_report import (
    explain_composite,
    explain_ratio_level,
    explain_ratio_vs_ma,
    explain_sector_row,
    explain_spread,
    generate_html_report,
)
from test_report_generator import _make_analysis


def _render(tmp_path, analysis=None):
    path = tmp_path / "report.html"
    generate_html_report(analysis or _make_analysis(), str(path))
    return path.read_text(encoding="utf-8")


# --- Rule-based readings ---


def test_explain_ratio_level_bands():
    assert "overbought" in explain_ratio_level(40.0, 23.4).lower()
    assert "oversold" in explain_ratio_level(5.0, 23.4).lower()
    assert "above" in explain_ratio_level(25.2, 23.4).lower()
    assert "below" in explain_ratio_level(15.0, 23.4).lower()


def test_explain_ratio_level_missing():
    assert explain_ratio_level(None, 23.4) == "No data."


def test_explain_ratio_vs_ma_direction():
    assert "improving" in explain_ratio_vs_ma(25.2, 20.5).lower()
    assert "fading" in explain_ratio_vs_ma(18.0, 22.0).lower()


def test_explain_composite_mentions_raw_score_when_penalised():
    text = explain_composite(46.9, 56.9, "Neutral")
    assert "56.9" in text
    assert "warning" in text.lower()


def test_explain_composite_without_penalty():
    text = explain_composite(72, 72, "Bull")
    assert "warning" not in text.lower()


def test_explain_spread_wide_vs_narrow():
    assert "selective" in explain_spread(47.7).lower()
    assert "even" in explain_spread(15.0).lower()


@pytest.mark.parametrize(
    "status,trend,keyword",
    [
        ("Overbought", "Up", "stretched"),
        ("Overbought", "Down", "rolling over"),
        ("Oversold", "Up", "recover"),
        ("Oversold", "Down", "avoid"),
        ("Normal", "Up", "strengthening"),
        ("Normal", "Down", "weakening"),
    ],
)
def test_explain_sector_row(status, trend, keyword):
    assert keyword in explain_sector_row(status, trend).lower()


# --- Rendered document ---


def test_html_is_complete_document(tmp_path):
    content = _render(tmp_path)
    assert content.startswith("<!doctype html>")
    assert "<title>" in content
    assert "</html>" in content


def test_html_has_main_sections(tmp_path):
    content = _render(tmp_path)
    for heading in (
        "How to read this report",
        "Overall Assessment",
        "Current Market Snapshot",
        "Component Scores",
        "Sector Heatmap",
    ):
        assert heading in content


def test_html_tables_have_explanation_columns(tmp_path):
    content = _render(tmp_path)
    assert "What it measures" in content
    assert "Today" in content


def test_html_shows_values(tmp_path):
    content = _render(tmp_path)
    assert "72" in content  # composite score
    assert "30.0%" in content  # uptrend ratio
    assert "Technology" in content


def test_html_warnings_section_only_when_warnings(tmp_path):
    assert "Active Warnings" in _render(tmp_path, _make_analysis(with_warnings=True))
    assert "Active Warnings" not in _render(tmp_path, _make_analysis(with_warnings=False))


def test_html_escapes_text(tmp_path):
    analysis = _make_analysis()
    analysis["composite"]["guidance"] = "<script>alert(1)</script>"
    content = _render(tmp_path, analysis)
    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;" in content


def test_html_survives_missing_components(tmp_path):
    analysis = _make_analysis()
    for comp in analysis["components"].values():
        comp["data_available"] = False
    content = _render(tmp_path, analysis)
    assert "Overall Assessment" in content


def test_html_report_write_error(tmp_path):
    bad_path = str(tmp_path / "nonexistent_dir" / "report.html")
    with pytest.raises(OSError):
        generate_html_report(_make_analysis(), bad_path)

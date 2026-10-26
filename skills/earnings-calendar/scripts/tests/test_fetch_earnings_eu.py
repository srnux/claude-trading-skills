"""Tests for the EU/UK earnings calendar fetcher (yfinance-backed).

All provider access is injected, so no network calls are made.
"""

import json
from datetime import date

import fetch_earnings_eu as eu
import pytest
from generate_report import generate_report

# ── Universe ──────────────────────────────────────────────────────────


def test_universe_covers_eu_and_uk_markets():
    universe = eu.load_universe()
    markets = {row["market"] for row in universe}
    assert markets == set(eu.MARKETS)
    symbols = {row["symbol"] for row in universe}
    assert {"SIE.DE", "ALV.DE", "MC.PA", "ASML.AS", "AZN.L", "NOVO-B.CO"} <= symbols


def test_universe_has_no_duplicate_symbols():
    symbols = [row["symbol"] for row in eu.load_universe()]
    assert len(symbols) == len(set(symbols))


def test_universe_market_filter_is_case_insensitive():
    universe = eu.load_universe(markets=["uk", "DE"])
    assert {row["market"] for row in universe} == {"UK", "DE"}


def test_universe_rejects_unknown_market():
    with pytest.raises(ValueError, match="XX"):
        eu.load_universe(markets=["DE", "XX"])


def test_parse_tickers_builds_custom_rows():
    rows = eu.parse_tickers("sie.de, AZN.L ,")
    assert [r["symbol"] for r in rows] == ["SIE.DE", "AZN.L"]
    assert all(r["market"] == "CUSTOM" for r in rows)


# ── Calendar parsing ──────────────────────────────────────────────────


def test_parse_calendar_single_confirmed_date():
    cal = {
        "Earnings Date": [date(2026, 11, 12)],
        "Earnings Average": 2.81246,
        "Revenue Average": 23239932540,
    }
    parsed = eu.parse_calendar(cal)
    assert parsed == {
        "date": "2026-11-12",
        "dateEstimated": False,
        "epsEstimated": 2.81246,
        "revenueEstimated": 23239932540,
    }


def test_parse_calendar_date_range_is_flagged_estimated():
    cal = {"Earnings Date": [date(2026, 11, 3), date(2026, 11, 7)]}
    parsed = eu.parse_calendar(cal)
    assert parsed["date"] == "2026-11-03"
    assert parsed["dateEstimated"] is True
    assert parsed["epsEstimated"] is None


@pytest.mark.parametrize(
    "cal", [None, {}, {"Earnings Date": []}, {"Ex-Dividend Date": date(2026, 1, 1)}]
)
def test_parse_calendar_without_earnings_date_returns_none(cal):
    assert eu.parse_calendar(cal) is None


# ── Money formatting ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,currency,expected",
    [
        (2.19e11, "EUR", "€219.0B"),
        (1.2e12, "EUR", "€1.2T"),
        (5.5e8, "GBP", "£550M"),
        (7.3e10, "DKK", "DKK 73.0B"),
        (None, "EUR", "N/A"),
    ],
)
def test_format_money(value, currency, expected):
    assert eu.format_money(value, currency) == expected


def test_normalize_currency_maps_pence_to_pounds():
    assert eu.normalize_currency("GBp") == "GBP"
    assert eu.normalize_currency("GBX") == "GBP"
    assert eu.normalize_currency("EUR") == "EUR"
    assert eu.normalize_currency(None) == "EUR"


# ── Record building (injected providers) ──────────────────────────────

UNIVERSE = [
    {"symbol": "SIE.DE", "name": "Siemens", "market": "DE", "country": "Germany"},
    {"symbol": "AZN.L", "name": "AstraZeneca", "market": "UK", "country": "United Kingdom"},
    {"symbol": "ALV.DE", "name": "Allianz", "market": "DE", "country": "Germany"},
    {"symbol": "BROKEN.DE", "name": "Broken", "market": "DE", "country": "Germany"},
]

CALENDARS = {
    "SIE.DE": {"Earnings Date": [date(2026, 11, 12)], "Earnings Average": 2.81},
    "AZN.L": {"Earnings Date": [date(2026, 10, 30)], "Earnings Average": 2.58},
    "ALV.DE": {"Earnings Date": [date(2026, 12, 20)]},  # outside window
}

INFOS = {
    "SIE.DE": {
        "longName": "Siemens Aktiengesellschaft",
        "currency": "EUR",
        "financialCurrency": "EUR",
        "marketCap": 2.0e11,
        "sector": "Industrials",
        "industry": "Specialty Industrial Machinery",
        "exchange": "GER",
    },
    "AZN.L": {
        "longName": "AstraZeneca PLC",
        "currency": "GBp",
        "financialCurrency": "USD",
        "marketCap": 2.0e11,
        "sector": "Healthcare",
        "industry": "Drug Manufacturers - General",
        "exchange": "LSE",
    },
}


def fake_calendar(symbol):
    if symbol == "BROKEN.DE":
        raise RuntimeError("404 Not Found")
    return CALENDARS.get(symbol, {})


def fake_info(symbol):
    return INFOS[symbol]


def fake_fx(currency):
    return {"EUR": 1.0, "GBP": 1.15}[currency]


def _build():
    return eu.build_records(
        UNIVERSE,
        date(2026, 10, 27),
        date(2026, 11, 13),
        fetch_calendar=fake_calendar,
        fetch_info=fake_info,
        fetch_fx=fake_fx,
    )


def test_build_records_keeps_only_in_window_sorted_by_date():
    records, failures = _build()
    assert [r["symbol"] for r in records] == ["AZN.L", "SIE.DE"]
    assert failures == ["BROKEN.DE"]


def test_build_records_converts_market_cap_to_eur():
    records, _ = _build()
    azn = records[0]
    assert azn["marketCapLocal"] == 2.0e11
    assert azn["currency"] == "GBP"
    assert azn["marketCap"] == pytest.approx(2.3e11)
    assert azn["marketCapFormatted"] == "€230.0B"


def test_build_records_matches_report_contract():
    records, _ = _build()
    required = {
        "symbol",
        "companyName",
        "date",
        "timing",
        "marketCap",
        "marketCapFormatted",
        "sector",
        "industry",
        "epsEstimated",
        "revenueEstimated",
        "exchange",
    }
    for record in records:
        assert required <= record.keys()
        assert record["region"] == "eu"
        assert record["timing"] == "TAS"
    azn = records[0]
    assert azn["companyName"] == "AstraZeneca PLC"
    assert azn["estimateCurrency"] == "USD"
    assert azn["market"] == "UK"


def test_build_records_survives_missing_info_and_fx():
    def no_info(symbol):
        raise RuntimeError("rate limited")

    def no_fx(currency):
        raise RuntimeError("fx down")

    records, failures = eu.build_records(
        UNIVERSE[:2],
        date(2026, 10, 27),
        date(2026, 11, 13),
        fetch_calendar=fake_calendar,
        fetch_info=no_info,
        fetch_fx=no_fx,
    )
    assert failures == []
    assert [r["symbol"] for r in records] == ["AZN.L", "SIE.DE"]
    assert records[0]["companyName"] == "AstraZeneca"  # universe name fallback
    assert records[0]["marketCap"] == 0
    assert records[0]["marketCapFormatted"] == "N/A"


# ── CLI ───────────────────────────────────────────────────────────────


def test_cli_rejects_bad_date(capsys):
    assert eu.main(["--from", "2026-13-01"]) == 1
    assert "Invalid" in capsys.readouterr().err


def test_cli_rejects_reversed_range(capsys):
    assert eu.main(["--from", "2026-11-10", "--to", "2026-11-01"]) == 1


def test_cli_rejects_unknown_market(capsys):
    assert eu.main(["--markets", "DE,XX"]) == 1
    assert "XX" in capsys.readouterr().err


def test_cli_writes_json_with_injected_providers(monkeypatch, capsys):
    monkeypatch.setattr(eu, "yf", object())  # pass the yfinance presence check
    monkeypatch.setattr(eu, "_providers", lambda: (fake_calendar, fake_info, fake_fx))
    rc = eu.main(["--from", "2026-10-27", "--to", "2026-11-13", "--tickers", "SIE.DE,AZN.L"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert [r["symbol"] for r in data] == ["AZN.L", "SIE.DE"]


def test_cli_exits_2_when_yfinance_missing(monkeypatch, capsys):
    """Absence test for the optional yfinance dependency."""
    monkeypatch.setattr(eu, "yf", None)
    assert eu.main(["--tickers", "SIE.DE"]) == 2
    err = capsys.readouterr().err
    assert "yfinance" in err
    assert "requirements.txt" in err


# ── Report generation for EU records ──────────────────────────────────


def test_eu_report_uses_eu_labels_and_currencies():
    records, _ = _build()
    report = generate_report(records)
    assert "yfinance" in report
    assert "Europe" in report
    assert "FMP API (US stocks" not in report
    assert "9:30 AM ET" not in report
    # Estimates shown in reporting currency, market cap in EUR
    assert "USD 2.58" in report
    assert "€2.81" in report
    assert "€230.0B" in report


def test_eu_report_marks_estimated_dates():
    records, _ = _build()
    records[0]["dateEstimated"] = True
    assert "| AZN.L* |" in generate_report(records)


def test_us_report_header_unchanged():
    us = [
        {
            "symbol": "AAPL",
            "companyName": "Apple",
            "date": "2026-10-29",
            "timing": "AMC",
            "marketCap": 3e12,
            "marketCapFormatted": "$3.0T",
            "sector": "Technology",
            "epsEstimated": 1.5,
            "revenueEstimated": 9e10,
        }
    ]
    report = generate_report(us)
    assert "FMP API (US stocks" in report
    assert "$1.50" in report

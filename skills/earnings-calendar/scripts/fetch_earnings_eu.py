#!/usr/bin/env python3
"""
EU/UK Earnings Calendar Fetcher (yfinance)

Retrieves upcoming earnings dates for European (EU + UK) large caps from
Yahoo Finance via yfinance, and outputs JSON in the same shape as
fetch_earnings_fmp.py so generate_report.py can render it.

Yahoo's market-wide earnings calendar is US-centric (it lists European
companies under their US OTC symbols), so this script walks a curated
universe of local listings (assets/eu_earnings_universe.csv) one ticker at a
time. No API key is required.

Usage:
    # Next 7 days, all markets
    python fetch_earnings_eu.py

    # Date range, selected markets
    python fetch_earnings_eu.py --from 2026-10-27 --to 2026-11-13 --markets DE,UK

    # Explicit tickers (Yahoo symbols), e.g. your holdings
    python fetch_earnings_eu.py --tickers SIE.DE,ALV.DE,AZN.L
"""

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

try:
    import yfinance as yf
except ImportError:  # optional: only this EU/UK mode needs it
    yf = None

DEFAULT_UNIVERSE = Path(__file__).resolve().parents[1] / "assets" / "eu_earnings_universe.csv"
MARKETS = ("DE", "FR", "NL", "IT", "ES", "UK", "NORDIC", "OTHER")
CURRENCY_SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$"}
PENCE_CODES = {"GBp", "GBX", "GBx"}


def load_universe(path: Path = DEFAULT_UNIVERSE, markets: Optional[list[str]] = None) -> list[dict]:
    """
    Load the ticker universe, optionally filtered by market code

    Args:
        path: CSV with columns symbol,name,market,country
        markets: Market codes to keep (case-insensitive); None keeps all

    Returns:
        List of universe rows

    Raises:
        ValueError: If an unknown market code is requested
    """
    wanted = None
    if markets:
        wanted = {m.strip().upper() for m in markets if m.strip()}
        unknown = sorted(wanted - set(MARKETS))
        if unknown:
            raise ValueError(
                f"Unknown market(s): {', '.join(unknown)}. Valid: {', '.join(MARKETS)}"
            )

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    return [row for row in rows if wanted is None or row["market"] in wanted]


def parse_tickers(arg: str) -> list[dict]:
    """
    Turn a comma-separated ticker list into universe rows

    Args:
        arg: e.g. "SIE.DE,AZN.L"

    Returns:
        Universe rows with market "CUSTOM"
    """
    symbols = [s.strip().upper() for s in arg.split(",") if s.strip()]
    return [{"symbol": s, "name": s, "market": "CUSTOM", "country": "N/A"} for s in symbols]


def parse_calendar(cal: Optional[dict]) -> Optional[dict]:
    """
    Extract the next earnings date and estimates from a yfinance calendar

    Yahoo returns one date when confirmed and a two-date window when the
    date is only projected; the window start is used and flagged.

    Args:
        cal: Ticker.calendar dict

    Returns:
        Parsed fields or None if no earnings date is known
    """
    if not cal:
        return None
    dates = cal.get("Earnings Date") or []
    if not dates:
        return None

    first = dates[0]
    if isinstance(first, datetime):
        first = first.date()

    return {
        "date": first.isoformat(),
        "dateEstimated": len(dates) > 1,
        "epsEstimated": cal.get("Earnings Average"),
        "revenueEstimated": cal.get("Revenue Average"),
    }


def normalize_currency(currency: Optional[str]) -> str:
    """
    Normalize Yahoo currency codes (UK quotes are in pence: GBp/GBX)

    Market cap from Ticker.info is already in major units, so only the
    code changes.
    """
    if not currency:
        return "EUR"
    if currency in PENCE_CODES:
        return "GBP"
    return currency.upper()


def format_money(value: Optional[float], currency: str) -> str:
    """
    Format an amount with its currency (e.g., "€219.0B", "DKK 73.0B")

    Args:
        value: Amount in major currency units
        currency: ISO currency code

    Returns:
        Formatted string or "N/A"
    """
    if value is None:
        return "N/A"
    prefix = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    if value >= 1e12:
        return f"{prefix}{value / 1e12:.1f}T"
    elif value >= 1e9:
        return f"{prefix}{value / 1e9:.1f}B"
    elif value >= 1e6:
        return f"{prefix}{value / 1e6:.0f}M"
    else:
        return f"{prefix}{value:,.0f}"


def build_records(
    universe: list[dict],
    start: date,
    end: date,
    fetch_calendar: Callable[[str], dict],
    fetch_info: Callable[[str], dict],
    fetch_fx: Callable[[str], float],
) -> tuple[list[dict], list[str]]:
    """
    Build report records for tickers with earnings inside [start, end]

    Company details and FX are only fetched for in-window tickers, so a
    full-universe run costs roughly one request per ticker.

    Args:
        universe: Universe rows
        start: Window start (inclusive)
        end: Window end (inclusive)
        fetch_calendar: symbol -> yfinance calendar dict
        fetch_info: symbol -> yfinance info dict
        fetch_fx: currency -> EUR per 1 unit

    Returns:
        (records sorted by date then EUR market cap desc, symbols whose
        calendar lookup failed)
    """
    records = []
    failures = []
    fx_cache: dict[str, Optional[float]] = {"EUR": 1.0}

    for i, row in enumerate(universe, 1):
        symbol = row["symbol"]
        try:
            parsed = parse_calendar(fetch_calendar(symbol))
        except Exception as e:
            print(f"  ⚠️  Warning: calendar lookup failed for {symbol}: {e}", file=sys.stderr)
            failures.append(symbol)
            continue

        if i % 50 == 0:
            print(f"  ✓ Checked {i}/{len(universe)} tickers", file=sys.stderr)

        if parsed is None:
            continue
        if not start.isoformat() <= parsed["date"] <= end.isoformat():
            continue

        try:
            info = fetch_info(symbol) or {}
        except Exception as e:
            print(f"  ⚠️  Warning: company info failed for {symbol}: {e}", file=sys.stderr)
            info = {}

        currency = normalize_currency(info.get("currency"))
        local_cap = info.get("marketCap")

        if currency not in fx_cache:
            try:
                fx_cache[currency] = fetch_fx(currency)
            except Exception as e:
                print(f"  ⚠️  Warning: FX rate failed for {currency}: {e}", file=sys.stderr)
                fx_cache[currency] = None
        rate = fx_cache[currency]

        eur_cap = local_cap * rate if local_cap and rate else None

        records.append(
            {
                "symbol": symbol,
                "companyName": info.get("longName") or row["name"],
                "date": parsed["date"],
                "dateEstimated": parsed["dateEstimated"],
                "timing": "TAS",
                "marketCap": eur_cap or 0,
                "marketCapFormatted": format_money(eur_cap, "EUR"),
                "marketCapLocal": local_cap,
                "currency": currency,
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "epsEstimated": parsed["epsEstimated"],
                "revenueEstimated": parsed["revenueEstimated"],
                "estimateCurrency": normalize_currency(info.get("financialCurrency") or currency),
                "fiscalDateEnding": None,
                "exchange": info.get("exchange", "N/A"),
                "market": row["market"],
                "country": row["country"],
                "region": "eu",
            }
        )

    records.sort(key=lambda r: (r["date"], -r["marketCap"]))
    return records, failures


def _providers() -> tuple[Callable, Callable, Callable]:
    """Return yfinance-backed (calendar, info, fx) fetchers."""

    def fetch_calendar(symbol: str) -> dict:
        return yf.Ticker(symbol).calendar

    def fetch_info(symbol: str) -> dict:
        return yf.Ticker(symbol).info

    def fetch_fx(currency: str) -> float:
        rate = yf.Ticker(f"{currency}EUR=X").fast_info["last_price"]
        if not rate:
            raise ValueError(f"no quote for {currency}EUR=X")
        return float(rate)

    return fetch_calendar, fetch_info, fetch_fx


def _parse_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch upcoming EU/UK earnings dates via yfinance (JSON to stdout)."
    )
    parser.add_argument("--from", dest="start", help="Start date YYYY-MM-DD (default: today)")
    parser.add_argument("--to", dest="end", help="End date YYYY-MM-DD (default: start + 7 days)")
    parser.add_argument(
        "--markets",
        help=f"Comma-separated market codes (default: all). Valid: {','.join(MARKETS)}",
    )
    parser.add_argument(
        "--tickers",
        help="Comma-separated Yahoo symbols (e.g. SIE.DE,AZN.L); replaces the universe",
    )
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE), help="Path to universe CSV")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Main execution"""
    args = build_parser().parse_args(argv)

    start = _parse_date(args.start) if args.start else date.today()
    if start is None:
        print(f"❌ ERROR: Invalid start date: {args.start} (expected YYYY-MM-DD)", file=sys.stderr)
        return 1
    end = _parse_date(args.end) if args.end else start + timedelta(days=7)
    if end is None:
        print(f"❌ ERROR: Invalid end date: {args.end} (expected YYYY-MM-DD)", file=sys.stderr)
        return 1
    if end < start:
        print("❌ ERROR: End date is before start date", file=sys.stderr)
        return 1

    try:
        if args.tickers:
            universe = parse_tickers(args.tickers)
        else:
            markets = args.markets.split(",") if args.markets else None
            universe = load_universe(Path(args.universe), markets)
    except ValueError as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        return 1

    if yf is None:
        print(
            "❌ ERROR: yfinance is not installed (required for EU/UK mode). "
            "Install with: pip install -r skills/earnings-calendar/requirements.txt",
            file=sys.stderr,
        )
        return 2

    print(
        f"📅 Fetching EU/UK earnings: {start} to {end} ({len(universe)} tickers)",
        file=sys.stderr,
    )
    fetch_calendar, fetch_info, fetch_fx = _providers()
    records, failures = build_records(universe, start, end, fetch_calendar, fetch_info, fetch_fx)

    if failures:
        print(f"⚠️  {len(failures)} ticker(s) failed: {', '.join(failures)}", file=sys.stderr)
    print(f"✓ Final dataset: {len(records)} companies", file=sys.stderr)
    print(json.dumps(records, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# VENDORED from scripts/fx/fx.py by scripts/sync_fx.py — do not edit.
# Edit the source and re-run: python3 scripts/sync_fx.py
"""USD -> EUR display helper for skills that print US-dollar prices.

Stdlib only. Fetches the live EUR/USD rate once from Yahoo's free chart
endpoint (EURUSD=X, unofficial, can lag) and formats prices as
"$165.40 (€149.60)". EUR = USD / rate.

Rate resolution, first match wins:
  1. enabled=False (the --no-eur flag)       -> None, USD only
  2. pin=RATE (the --eurusd flag)            -> that rate
  3. INTRADAY_EURUSD env: "off" -> None, a number -> that rate
  4. offline=True (replaying saved files)    -> None, never touches the network
  5. live fetch; any failure                 -> None, USD only

Never raises on a network problem: a missing rate only drops the EUR part.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

BANNER = (
    "# VENDORED from scripts/fx/fx.py by scripts/sync_fx.py — do not edit.\n"
    "# Edit the source and re-run: python3 scripts/sync_fx.py\n"
)

ENV_VAR = "INTRADAY_EURUSD"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=5m&range=1d"
_UA = "Mozilla/5.0 (compatible; trading-skills-fx/1.0)"


@dataclass(frozen=True)
class FxRate:
    rate: float  # US dollars per 1 euro
    as_of: str  # ISO 8601 UTC, e.g. 2026-11-12T18:15:00Z
    source: str  # "yahoo EURUSD=X", "pinned" or "env"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http_get(url: str, timeout: float = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https URL)
        return r.read().decode("utf-8", "replace")


def _parse_rate(value: str, where: str) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{where}: EUR/USD rate must be a number or 'off', got {value!r}")
    if not 0.5 < rate < 2.5:
        raise ValueError(f"{where}: EUR/USD rate {rate} is outside 0.5-2.5")
    return rate


def _from_chart(text: str) -> FxRate | None:
    result = json.loads(text)["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    stamps = result["timestamp"]
    for close, ts in zip(reversed(closes), reversed(stamps)):
        if close:
            as_of = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return FxRate(rate=round(float(close), 4), as_of=as_of, source="yahoo EURUSD=X")
    return None


def resolve(enabled=True, pin=None, offline=False, fetch=None) -> FxRate | None:
    """Return the EUR/USD rate to display with, or None for USD only."""
    if not enabled:
        return None
    if pin is not None:
        return FxRate(rate=_parse_rate(pin, "--eurusd"), as_of=_now_iso(), source="pinned")
    env = os.environ.get(ENV_VAR, "").strip()
    if env.lower() == "off":
        return None
    if env:
        return FxRate(rate=_parse_rate(env, ENV_VAR), as_of=_now_iso(), source="env")
    if offline:
        return None
    try:
        return _from_chart((fetch or _http_get)(YAHOO_URL))
    except Exception:  # noqa: BLE001 - any failure only drops the EUR display
        return None


def add_cli_flags(parser) -> None:
    """Add --eurusd and --no-eur to an argparse (sub)parser."""
    parser.add_argument(
        "--eurusd",
        type=float,
        default=None,
        help="pin the EUR/USD rate (dollars per euro) instead of fetching it live",
    )
    parser.add_argument(
        "--no-eur", action="store_true", help="show US dollars only, no euro conversion"
    )


def from_args(args, offline=False) -> FxRate | None:
    """resolve() from parsed --eurusd / --no-eur flags."""
    return resolve(
        enabled=not getattr(args, "no_eur", False),
        pin=getattr(args, "eurusd", None),
        offline=offline,
    )


def eur(usd, rate: FxRate | None) -> float | None:
    """The euro amount, rounded to the cent, or None without a rate."""
    if rate is None or usd is None:
        return None
    return round(float(usd) / rate.rate, 2)


def eur_only(usd, rate: FxRate | None) -> str:
    """'€149.60', or '' without a rate."""
    value = eur(usd, rate)
    return "" if value is None else f"€{value:,.2f}"


def usd_eur(usd, rate: FxRate | None) -> str:
    """'$165.40 (€149.60)', or '$165.40' without a rate."""
    text = f"${float(usd):,.2f}"
    value = eur(usd, rate)
    return text if value is None else f"{text} (€{value:,.2f})"


def to_json(rate: FxRate | None) -> dict | None:
    """The 'fx' block for JSON reports."""
    if rate is None:
        return None
    return {"eurusd": rate.rate, "as_of": rate.as_of, "source": rate.source}


def note(rate: FxRate | None) -> str:
    """One line naming the rate used, or '' without a rate."""
    if rate is None:
        return ""
    return (
        f"Euro prices at 1 € = ${rate.rate:.4f} ({rate.source}, {rate.as_of}); "
        "broker EUR quotes from European venues can differ by a few cents."
    )

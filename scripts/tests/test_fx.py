"""Tests for the shared USD -> EUR display helper (scripts/fx/fx.py) and its vendored copies."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "scripts" / "fx" / "fx.py"


def _load():
    spec = importlib.util.spec_from_file_location("fx_under_test", SOURCE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


fx = _load()


def _chart(closes, timestamps):
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": timestamps,
                        "indicators": {"quote": [{"close": closes}]},
                    }
                ]
            }
        }
    )


def test_pinned_rate_from_argument():
    rate = fx.resolve(pin=1.1)
    assert rate.rate == pytest.approx(1.1)
    assert rate.source == "pinned"


def test_env_off_disables(monkeypatch):
    monkeypatch.setenv("INTRADAY_EURUSD", "off")
    assert fx.resolve(fetch=lambda url: pytest.fail("must not fetch")) is None


def test_env_number_pins(monkeypatch):
    monkeypatch.setenv("INTRADAY_EURUSD", "1.25")
    rate = fx.resolve(fetch=lambda url: pytest.fail("must not fetch"))
    assert rate.rate == pytest.approx(1.25)


def test_disabled_flag_wins_over_env(monkeypatch):
    monkeypatch.setenv("INTRADAY_EURUSD", "1.25")
    assert fx.resolve(enabled=False) is None


def test_offline_never_fetches(monkeypatch):
    monkeypatch.delenv("INTRADAY_EURUSD", raising=False)
    assert fx.resolve(offline=True, fetch=lambda url: pytest.fail("must not fetch")) is None


def test_live_fetch_takes_last_non_null_close(monkeypatch):
    monkeypatch.delenv("INTRADAY_EURUSD", raising=False)
    seen = []

    def fake(url):
        seen.append(url)
        return _chart([1.10, 1.1056, None], [1762970100, 1762970400, 1762970700])

    rate = fx.resolve(fetch=fake)
    assert "EURUSD=X" in seen[0]
    assert rate.rate == pytest.approx(1.1056)
    assert rate.source == "yahoo EURUSD=X"
    assert rate.as_of.startswith("2025-11-12T")


def test_fetch_failure_degrades_to_none(monkeypatch):
    monkeypatch.delenv("INTRADAY_EURUSD", raising=False)

    def boom(url):
        raise OSError("offline")

    assert fx.resolve(fetch=boom) is None


def test_bad_env_value_raises(monkeypatch):
    monkeypatch.setenv("INTRADAY_EURUSD", "abc")
    with pytest.raises(ValueError):
        fx.resolve()


def test_formatting_with_and_without_rate():
    rate = fx.FxRate(rate=1.1056, as_of="2026-11-12T18:15:00Z", source="pinned")
    assert fx.eur(165.40, rate) == pytest.approx(149.60)
    assert fx.usd_eur(165.40, rate) == "$165.40 (€149.60)"
    assert fx.usd_eur(1234.5, rate) == "$1,234.50 (€1,116.59)"
    assert fx.usd_eur(165.40, None) == "$165.40"
    assert fx.eur(165.40, None) is None
    assert fx.eur_only(165.40, rate) == "€149.60"
    assert fx.eur_only(165.40, None) == ""


def test_json_block_and_note():
    rate = fx.FxRate(rate=1.1056, as_of="2026-11-12T18:15:00Z", source="yahoo EURUSD=X")
    assert fx.to_json(rate) == {
        "eurusd": 1.1056,
        "as_of": "2026-11-12T18:15:00Z",
        "source": "yahoo EURUSD=X",
    }
    assert fx.to_json(None) is None
    assert "1 € = $1.1056" in fx.note(rate)
    assert fx.note(None) == ""


def test_vendored_copies_match_source():
    """Every skills/*/scripts/_fx.py must be byte-identical to the source plus banner."""
    expected = fx.BANNER + SOURCE.read_text(encoding="utf-8")
    copies = sorted(REPO_ROOT.glob("skills/*/scripts/_fx.py"))
    assert copies, "no vendored _fx.py found"
    stale = [
        str(p.relative_to(REPO_ROOT)) for p in copies if p.read_text(encoding="utf-8") != expected
    ]
    assert not stale, f"stale _fx.py copies, run python3 scripts/sync_fx.py: {stale}"

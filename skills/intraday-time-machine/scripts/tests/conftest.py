"""Put this skill's scripts/ folder on sys.path for its tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _usd_only_by_default(monkeypatch):
    """Keep tests offline and USD-only: no live EUR/USD fetch. EUR tests pin a rate."""
    monkeypatch.setenv("INTRADAY_EURUSD", "off")

"""Shared fixtures for Position Sizer tests"""

import os
import sys

# Add scripts directory to path so modules can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Add tests directory to path so helpers can be imported
sys.path.insert(0, os.path.dirname(__file__))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _usd_only_by_default(monkeypatch):
    """Keep tests offline and USD-only: no live EUR/USD fetch. EUR tests pin a rate."""
    monkeypatch.setenv("INTRADAY_EURUSD", "off")

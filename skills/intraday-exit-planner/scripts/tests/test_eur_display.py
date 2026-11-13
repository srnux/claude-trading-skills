"""EUR display: every dollar price also shows euros; the USD plan fields never change."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout

import _fx
import intraday_exit as exitp
import pytest

FLAGS = [
    "plan",
    "--now",
    "2026-10-19 10:16",
    "--symbol",
    "TSLA",
    "--entry",
    "364.18",
    "--or-high",
    "362.18",
    "--or-low",
    "354.47",
    "--time",
    "10:15",
    "--entry-bar",
    "8",
    "--date",
    "2026-10-19",
    "--target",
    "1R",
]
USD = {"entry": 364.18, "stop": 358.32, "target": 370.04, "risk_per_share": 5.86}


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = exitp.main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    return tmp_path


def test_json_gets_fx_and_eur_siblings_and_keeps_usd(workdir):
    code, text, err = run(FLAGS + ["--eurusd", "1.1", "--json", "--no-write"])
    assert code == 0, err
    p = json.loads(text)
    for k, v in USD.items():
        assert p[k] == v and isinstance(p[k], float)
        assert p[k + "_eur"] == round(v / 1.1, 2)
    assert p["fx"]["eurusd"] == 1.1
    assert p["fx"]["source"] == "pinned"
    assert p["fx"]["as_of"]


def test_without_a_rate_eur_fields_and_fx_are_null(workdir):
    code, text, _ = run(FLAGS + ["--json", "--no-write"])
    assert code == 0
    p = json.loads(text)
    assert p["fx"] is None
    assert all(p[k + "_eur"] is None for k in USD)
    code, text, _ = run(FLAGS + ["--no-write"])
    assert "€" not in text and "Euro prices" not in text


def test_terminal_and_markdown_show_euros_and_the_rate_once(workdir, monkeypatch):
    monkeypatch.setenv("INTRADAY_EURUSD", "1.1")
    code, text, err = run(FLAGS)
    assert code == 0, err
    assert "Entry         $364.18 (€331.07) at 10:15 AM (bar 8)" in text
    assert "Stop          $358.32 (€325.75)  opening-range midpoint" in text
    assert "Target        $370.04 (€336.40)  1R" in text
    assert "Risk a share  $5.86 (€5.33) (1.61% of the entry)" in text
    assert text.count("Euro prices at 1 € = $1.1000") == 1
    md = (workdir / "reports" / "intraday_exit_plan_TSLA_2026-10-19.md").read_text("utf-8")
    assert "$364.18 (€331.07)" in md
    assert md.count("Euro prices at 1 € = $1.1000") == 1
    saved = json.loads(
        (workdir / "reports" / "intraday_exit_plan_TSLA_2026-10-19.json").read_text()
    )
    assert saved["entry"] == 364.18 and saved["entry_eur"] == 331.07
    assert saved["fx"]["source"] == "env"


def test_show_converts_with_its_own_flags(workdir):
    assert run(FLAGS)[0] == 0  # USD-only plan on disk
    code, text, _ = run(["show", "--now", "2026-10-19 10:20", "--eurusd", "1.1"])
    assert code == 0
    assert "Target        $370.04 (€336.40)" in text
    assert "Euro prices at 1 € = $1.1000" in text
    code, text, _ = run(["show", "--now", "2026-10-19 10:20", "--eurusd", "1.1", "--no-eur"])
    assert "€" not in text


def test_no_eur_beats_the_env(workdir, monkeypatch):
    monkeypatch.setenv("INTRADAY_EURUSD", "1.1")
    code, text, _ = run(FLAGS + ["--no-eur", "--json", "--no-write"])
    p = json.loads(text)
    assert p["fx"] is None and p["entry_eur"] is None


def test_an_offline_replay_never_fetches_the_rate(workdir, monkeypatch):
    monkeypatch.delenv("INTRADAY_EURUSD", raising=False)
    calls = []
    monkeypatch.setattr(_fx, "_http_get", lambda *a, **k: calls.append(a) or "{}")
    tsla = os.path.join(os.path.dirname(__file__), "fixtures", "TSLA-2026-10-19-5m.json")
    code, text, err = run(FLAGS + ["--stop", "atr:1.5", "--offline", tsla, "--json", "--no-write"])
    assert code == 0, err
    assert calls == []
    assert json.loads(text)["fx"] is None


def test_the_rate_is_resolved_once_per_run(workdir, monkeypatch):
    monkeypatch.delenv("INTRADAY_EURUSD", raising=False)
    calls = []
    real = _fx.resolve

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(_fx, "resolve", counting)
    run(FLAGS + ["--eurusd", "1.1"])
    assert len(calls) == 1


def test_a_bad_rate_is_a_one_line_error(workdir, monkeypatch):
    code, _, err = run(FLAGS + ["--eurusd", "9", "--no-write"])
    assert code == 1
    assert err.startswith("intraday_exit.py: --eurusd: EUR/USD rate 9.0 is outside")
    monkeypatch.setenv("INTRADAY_EURUSD", "abc")
    code, _, err = run(FLAGS + ["--no-write"])
    assert code == 1 and "INTRADAY_EURUSD" in err and "Traceback" not in err

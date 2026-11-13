"""Intraday mode: size one intraday-exit-planner plan into one whole-share bracket order.

The numbers reproduce the TSLA example of Monday 2026-10-19: entry 364.18 at 10:15 AM,
stop 358.32 (opening-range midpoint), target 370.04 (1R), a $5,000 account with a
10% cash buffer and a $50 max loss per trade.
"""

import datetime
import json
import os

import pytest
from intraday_mode import (
    IntradayLimits,
    IntradaySizingError,
    bracket_order,
    fresh_price,
    load_plan,
    size_intraday,
)
from position_sizer import generate_markdown_report, main

PLAN = {
    "created_by": "intraday-exit-planner",
    "symbol": "TSLA",
    "side": "buy",
    "date": "2026-10-19",
    "setup": "orb",
    "entry": 364.18,
    "entry_time": "10:15 AM",
    "entry_bar": 8,
    "interval": "5m",
    "opening_range": {"high": 362.18, "low": 354.47, "minutes": 15},
    "stop": 358.32,
    "stop_rule": "or_mid",
    "stop_label": "opening-range midpoint",
    "target": 370.04,
    "target_r": 1.0,
    "target_label": "1R (one times the risk)",
    "risk_per_share": 5.86,
    "reward_risk": 1.0,
    "flat_by": "15:55",
}

EXAMPLE = IntradayLimits(
    account_size=5000,
    max_loss_usd=50,
    max_position_pct=75,
    max_order_usd=4000,
    cash_buffer_pct=10,
    min_order_usd=5,
    min_reward_risk=1.0,
)


def limit_by_name(result):
    return {lim["type"]: lim for lim in result["constraints_applied"]}


class TestSizing:
    def test_tsla_is_8_shares_bound_by_the_max_loss(self):
        r = size_intraday(PLAN, EXAMPLE, today="2026-10-19")
        assert r["mode"] == "intraday"
        assert r["final_recommended_shares"] == 8
        assert r["binding_constraint"] == "max_loss"
        assert r["final_position_value"] == 2913.44
        assert r["final_risk_dollars"] == 46.88
        assert r["final_risk_pct"] == 0.94
        assert r["refusal"] is None
        lims = limit_by_name(r)
        assert [
            lims[k]["max_shares"] for k in ("max_loss", "max_position_pct", "max_order", "cash")
        ] == [
            8,
            10,
            10,
            12,
        ]
        assert lims["max_loss"]["binding"] is True
        assert lims["cash"]["binding"] is False

    def test_the_bracket_order_is_place_stock_order_shaped(self):
        r = size_intraday(PLAN, EXAMPLE, today="2026-10-19")
        o = r["bracket_order"]
        assert {k: o[k] for k in o if k not in ("why", "plan")} == {
            "symbol": "TSLA",
            "side": "buy",
            "qty": "8",
            "type": "market",
            "time_in_force": "day",
            "order_class": "bracket",
            "take_profit_limit_price": "370.04",
            "stop_loss_stop_price": "358.32",
        }
        assert "bound by your $50 max loss per trade" in o["why"]
        assert o["plan"]["max_loss"] == 46.88
        assert o["plan"]["flat_by"] == "15:55"

    def test_a_limit_order_sizes_at_the_limit(self):
        r = size_intraday(PLAN, EXAMPLE, limit_price=364.00, today="2026-10-19")
        o = r["bracket_order"]
        assert (o["type"], o["limit_price"]) == ("limit", "364.00")
        assert r["parameters"]["sized_at"] == 364.00
        assert r["parameters"]["sized_from"] == "limit"

    def test_each_limit_can_bind(self):
        r = size_intraday(
            PLAN, IntradayLimits(account_size=5000, max_loss_usd=500), today="2026-10-19"
        )
        assert (r["final_recommended_shares"], r["binding_constraint"]) == (13, "cash")
        lim = IntradayLimits(account_size=5000, max_loss_usd=500, max_order_usd=1000)
        assert size_intraday(PLAN, lim, today="2026-10-19")["binding_constraint"] == "max_order"
        lim = IntradayLimits(account_size=5000, max_loss_usd=500, max_position_pct=20)
        assert (
            size_intraday(PLAN, lim, today="2026-10-19")["binding_constraint"] == "max_position_pct"
        )

    def test_available_cash_caps_the_size(self):
        lim = IntradayLimits(
            account_size=5000, max_loss_usd=500, cash_buffer_pct=10, available_cash=1500
        )
        r = size_intraday(PLAN, lim, today="2026-10-19")
        assert (r["final_recommended_shares"], r["binding_constraint"]) == (2, "cash")
        assert (
            "available cash $1,500.00 minus the $500.00 buffer" in limit_by_name(r)["cash"]["how"]
        )

    def test_risk_pct_sets_the_max_loss(self):
        lim = IntradayLimits(account_size=5000, risk_pct=1.0)
        r = size_intraday(PLAN, lim, today="2026-10-19")
        assert r["parameters"]["max_loss_usd"] == 50.0
        assert r["final_recommended_shares"] == 8


class TestRefusals:
    def test_a_stop_too_far_for_the_max_loss_is_a_refusal_not_a_smaller_order(self):
        r = size_intraday(dict(PLAN, stop=300.0), EXAMPLE, today="2026-10-19")
        assert r["final_recommended_shares"] == 0
        assert r["bracket_order"] is None
        assert "one share risks $64.18" in r["refusal"]
        assert "more than your $50.00 max loss per trade" in r["refusal"]

    def test_a_fresh_higher_price_means_a_bigger_risk_and_can_fail_reward_risk(self):
        r = size_intraday(PLAN, EXAMPLE, current_price=366.48, today="2026-10-19")
        assert r["parameters"]["sized_at"] == 366.48
        assert r["parameters"]["sized_from"] == "current_price"
        assert r["parameters"]["risk_per_share"] == 8.16
        assert r["parameters"]["reward_risk"] == 0.44
        assert r["bracket_order"] is None
        assert "reward:risk 0.44" in r["refusal"]
        assert "under your minimum 1.0" in r["refusal"]

    def test_a_lower_price_never_shrinks_the_risk(self):
        r = size_intraday(PLAN, EXAMPLE, current_price=360.00, today="2026-10-19")
        assert r["parameters"]["sized_at"] == 364.18
        assert r["final_recommended_shares"] == 8

    def test_a_target_at_or_under_the_entry_means_the_move_happened(self):
        r = size_intraday(PLAN, EXAMPLE, current_price=371.00, today="2026-10-19")
        assert r["bracket_order"] is None
        assert "the move has already happened" in r["refusal"]

    def test_under_the_minimum_order(self):
        lim = IntradayLimits(account_size=5000, max_loss_usd=50, min_order_usd=5000)
        r = size_intraday(PLAN, lim, today="2026-10-19")
        assert r["bracket_order"] is None
        assert "under your $5,000.00 minimum order" in r["refusal"]

    @pytest.mark.parametrize(
        "plan, message",
        [
            (dict(PLAN, side="sell"), r"long \(buy\) day trades only"),
            (dict(PLAN, stop=None), "needs a positive stop"),
            (dict(PLAN, stop=365.0), "is not below the entry"),
            (dict(PLAN, symbol=""), "has no symbol"),
        ],
    )
    def test_bad_plans(self, plan, message):
        with pytest.raises(IntradaySizingError, match=message):
            size_intraday(plan, EXAMPLE, today="2026-10-19")

    def test_a_plan_for_another_day(self):
        with pytest.raises(
            IntradaySizingError, match="the plan is for 2026-10-19 and today is 2026-10-20"
        ):
            size_intraday(PLAN, EXAMPLE, today="2026-10-20")

    @pytest.mark.parametrize(
        "limits, message",
        [
            (IntradayLimits(account_size=5000), "needs --max-loss-usd or --risk-pct"),
            (
                IntradayLimits(account_size=5000, max_loss_usd=50, cash_buffer_pct=100),
                "cash buffer",
            ),
            (IntradayLimits(account_size=5000, max_loss_usd=-1), "max loss"),
        ],
    )
    def test_bad_limits(self, limits, message):
        with pytest.raises(IntradaySizingError, match=message):
            size_intraday(PLAN, limits, today="2026-10-19")

    def test_bracket_order_is_none_on_a_refusal(self):
        assert bracket_order({"refusal": "no", "final_recommended_shares": 0}) is None


class TestInputs:
    def test_load_plan_reads_the_exit_planner_report(self, tmp_path):
        p = tmp_path / "intraday_exit_plan_TSLA_2026-10-19.json"
        p.write_text(json.dumps(PLAN))
        assert load_plan(str(p))["symbol"] == "TSLA"

    def test_load_plan_errors(self, tmp_path):
        with pytest.raises(IntradaySizingError, match="no plan at"):
            load_plan(str(tmp_path / "missing.json"))
        bad = tmp_path / "bad.json"
        bad.write_text("{nope")
        with pytest.raises(IntradaySizingError, match="not valid JSON"):
            load_plan(str(bad))
        lst = tmp_path / "list.json"
        lst.write_text("[]")
        with pytest.raises(IntradaySizingError, match="not a plan"):
            load_plan(str(lst))

    def test_fresh_price_from_the_alerts_prices_file(self):
        doc = {
            "as_of": "2026-10-19T14:53:00Z",
            "prices": {"TSLA": 366.475},
            "detail": {"TSLA": {"time": "2026-10-19T14:52:13Z"}},
        }
        now = datetime.datetime(2026, 10, 19, 14, 55)
        assert fresh_price(doc, "TSLA", now) == (366.475, True)
        later = datetime.datetime(2026, 10, 19, 15, 30)
        assert fresh_price(doc, "TSLA", later) == (366.475, False)
        assert fresh_price(doc, "AAPL", now) == (None, False)
        assert fresh_price({"prices": {"TSLA": 1.0}}, "TSLA", now) == (1.0, False)


class TestCli:
    def run(self, monkeypatch, tmp_path, *args):
        monkeypatch.setattr(
            "sys.argv", ["position_sizer.py", "--output-dir", str(tmp_path / "out"), *args]
        )
        try:
            main()
            return 0
        except SystemExit as e:
            return e.code

    def write_plan(self, tmp_path, plan=PLAN):
        p = tmp_path / "intraday_exit_plan_TSLA_2026-10-19.json"
        p.write_text(json.dumps(plan))
        return str(p)

    def read_report(self, tmp_path):
        out = tmp_path / "out"
        (name,) = [n for n in os.listdir(out) if n.endswith(".json")]
        with open(out / name) as fh:
            return json.load(fh), (out / name.replace(".json", ".md")).read_text()

    def test_cli_writes_the_bracket_order(self, monkeypatch, tmp_path, capsys):
        plan = self.write_plan(tmp_path)
        code = self.run(
            monkeypatch,
            tmp_path,
            "--intraday-plan",
            plan,
            "--account-size",
            "5000",
            "--max-loss-usd",
            "50",
            "--max-position-pct",
            "75",
            "--max-order-usd",
            "4000",
            "--cash-buffer-pct",
            "10",
            "--today",
            "2026-10-19",
        )
        assert code == 0
        doc, md = self.read_report(tmp_path)
        assert doc["final_recommended_shares"] == 8
        assert doc["bracket_order"]["qty"] == "8"
        assert "## Proposed Bracket Order" in md
        assert "buy 8 TSLA, market, day, take-profit 370.04, stop-loss 358.32" in md
        out = capsys.readouterr().out
        assert "Final: 8 shares of TSLA" in out
        assert "Nothing was placed" in out

    def test_cli_refusal_exits_1_and_still_writes_the_report(self, monkeypatch, tmp_path, capsys):
        plan = self.write_plan(tmp_path, dict(PLAN, stop=300.0))
        code = self.run(
            monkeypatch,
            tmp_path,
            "--intraday-plan",
            plan,
            "--account-size",
            "5000",
            "--max-loss-usd",
            "50",
            "--today",
            "2026-10-19",
        )
        assert code == 1
        doc, md = self.read_report(tmp_path)
        assert doc["bracket_order"] is None
        assert "No order:" in md
        assert "No order:" in capsys.readouterr().out

    def test_cli_reads_a_fresh_price_from_the_prices_file(self, monkeypatch, tmp_path):
        plan = self.write_plan(tmp_path)
        prices = tmp_path / "prices.json"
        prices.write_text(
            json.dumps(
                {"prices": {"TSLA": 366.48}, "detail": {"TSLA": {"time": "2026-10-19T14:52:13Z"}}}
            )
        )
        code = self.run(
            monkeypatch,
            tmp_path,
            "--intraday-plan",
            plan,
            "--account-size",
            "5000",
            "--max-loss-usd",
            "50",
            "--prices-file",
            str(prices),
            "--now",
            "2026-10-19T14:55:00Z",
        )
        assert code == 1
        doc, _ = self.read_report(tmp_path)
        assert doc["parameters"]["sized_from"] == "current_price"
        assert "reward:risk 0.44" in doc["refusal"]

    @pytest.mark.parametrize(
        "extra",
        [
            ["--fractional"],
            ["--atr", "3.2"],
            ["--win-rate", "0.5", "--avg-win", "2", "--avg-loss", "1"],
            ["--entry", "364.18"],
        ],
    )
    def test_cli_rejects_other_modes_with_a_plan(self, monkeypatch, tmp_path, capsys, extra):
        plan = self.write_plan(tmp_path)
        code = self.run(
            monkeypatch,
            tmp_path,
            "--intraday-plan",
            plan,
            "--account-size",
            "5000",
            "--max-loss-usd",
            "50",
            *extra,
        )
        assert code == 2
        assert "--intraday-plan" in capsys.readouterr().err

    def test_cli_plan_errors_are_one_line(self, monkeypatch, tmp_path, capsys):
        code = self.run(
            monkeypatch,
            tmp_path,
            "--intraday-plan",
            str(tmp_path / "nope.json"),
            "--account-size",
            "5000",
            "--max-loss-usd",
            "50",
        )
        assert code == 1
        err = capsys.readouterr().err
        assert err.startswith("Error: no plan at")

    def test_markdown_for_an_intraday_result(self):
        r = size_intraday(PLAN, EXAMPLE, today="2026-10-19")
        md = generate_markdown_report(r)
        assert "**Mode:** intraday" in md
        assert "| max_loss | $50.00 max loss / 5.86 risk a share | 8 | yes |" in md
        assert "Max loss at the stop: 8 x 5.86 = $46.88" in md


# ---------------------------------------------------------------- EUR display

import _fx  # noqa: E402

RATE = _fx.FxRate(rate=1.1, as_of="2026-10-19T14:15:00Z", source="pinned")
EUR_PARAMS = {
    "entry_plan": 331.07,
    "sized_at": 331.07,
    "stop_price": 325.75,
    "target_price": 336.4,
    "risk_per_share": 5.33,
    "account_size": 4545.45,
    "cash_buffer_usd": 454.55,
}


class TestEur:
    def test_eur_siblings_and_fx_without_touching_the_usd_result(self):
        usd = size_intraday(PLAN, EXAMPLE, today="2026-10-19")
        r = size_intraday(PLAN, EXAMPLE, today="2026-10-19", fx_rate=RATE)
        assert r["fx"] == {"eurusd": 1.1, "as_of": "2026-10-19T14:15:00Z", "source": "pinned"}
        p = r["parameters"]
        for k, v in EUR_PARAMS.items():
            name = "cash_buffer_eur" if k == "cash_buffer_usd" else k + "_eur"
            assert p[name] == v, name
        assert p["max_loss_eur"] == 45.45
        assert r["final_position_value_eur"] == 2648.58
        assert r["final_risk_eur"] == 42.62
        assert r["max_loss_at_stop_eur"] == 42.62
        lims = limit_by_name(r)
        assert lims["max_loss"]["limit_eur"] == 45.45
        assert lims["max_order"]["limit_eur"] == 3636.36
        # every USD field, share count and the Alpaca order fields are unchanged
        for k, v in usd["parameters"].items():
            if not k.endswith("_eur"):
                assert p[k] == v and type(p[k]) is type(v), k
        for k in ("final_recommended_shares", "final_position_value", "final_risk_dollars"):
            assert r[k] == usd[k]
        strip = ("why", "plan")
        assert {k: v for k, v in r["bracket_order"].items() if k not in strip} == {
            k: v for k, v in usd["bracket_order"].items() if k not in strip
        }

    def test_without_a_rate_the_eur_fields_are_null(self):
        r = size_intraday(PLAN, EXAMPLE, today="2026-10-19")
        assert r["fx"] is None
        assert r["parameters"]["sized_at_eur"] is None
        assert r["final_position_value_eur"] is None
        assert all(c["limit_eur"] is None for c in r["constraints_applied"])
        assert "€" not in generate_markdown_report(r)

    def test_markdown_shows_euros_and_the_rate_once(self):
        md = generate_markdown_report(
            size_intraday(PLAN, EXAMPLE, today="2026-10-19", fx_rate=RATE)
        )
        assert "- **Sized at:** 364.18 (€331.07) (plan)" in md
        assert "**Stop:** 358.32 (€325.75)  **Target:** 370.04 (€336.40)" in md
        assert "**Risk a share:** 5.86 (€5.33)" in md
        assert "| max_loss | $50.00 (€45.45) max loss / 5.86 risk a share | 8 | yes |" in md
        assert "Max loss at the stop: 8 x 5.86 = $46.88 (€42.62)" in md
        assert "**Shares:** 8 = $2,913.44 (€2,648.58)" in md
        assert "buy 8 TSLA, market, day, take-profit 370.04, stop-loss 358.32" in md
        assert md.count("Euro prices at 1 € = $1.1000") == 1

    def test_refusal_text_shows_euros(self):
        r = size_intraday(dict(PLAN, stop=300.0), EXAMPLE, today="2026-10-19", fx_rate=RATE)
        assert "one share risks $64.18 (€58.35)" in r["refusal"]
        assert "your $50.00 (€45.45) max loss per trade" in r["refusal"]


class TestEurCli:
    run = TestCli.run
    write_plan = TestCli.write_plan
    read_report = TestCli.read_report

    def size(self, monkeypatch, tmp_path, *extra):
        plan = self.write_plan(tmp_path)
        return self.run(
            monkeypatch,
            tmp_path,
            "--intraday-plan",
            plan,
            "--account-size",
            "5000",
            "--max-loss-usd",
            "50",
            "--max-position-pct",
            "75",
            "--max-order-usd",
            "4000",
            "--cash-buffer-pct",
            "10",
            "--today",
            "2026-10-19",
            *extra,
        )

    def test_cli_pinned_rate(self, monkeypatch, tmp_path, capsys):
        assert self.size(monkeypatch, tmp_path, "--eurusd", "1.1") == 0
        doc, md = self.read_report(tmp_path)
        assert doc["fx"]["eurusd"] == 1.1 and doc["fx"]["source"] == "pinned"
        assert doc["parameters"]["sized_at"] == 364.18
        assert doc["parameters"]["sized_at_eur"] == 331.07
        out = capsys.readouterr().out
        assert "Final: 8 shares of TSLA @ 364.18 (€331.07)" in out
        assert "Account $5,000.00 (€4,545.45), max loss $50.00 (€45.45)" in out
        assert "max order $4,000.00 (€3,636.36)" in out
        assert "Order value $2,913.44 (€2,648.58)" in out
        assert "$46.88 (€42.62)" in out
        assert out.count("Euro prices at 1 € = $1.1000") == 1

    def test_cli_env_rate_and_no_eur(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("INTRADAY_EURUSD", "1.1")
        assert self.size(monkeypatch, tmp_path, "--no-eur") == 0
        doc, md = self.read_report(tmp_path)
        assert doc["fx"] is None
        assert "€" not in capsys.readouterr().out and "€" not in md

    def test_cli_bad_rate_is_one_line(self, monkeypatch, tmp_path, capsys):
        assert self.size(monkeypatch, tmp_path, "--eurusd", "9") == 1
        assert capsys.readouterr().err.startswith("Error: --eurusd: EUR/USD rate 9.0")

    def test_classic_mode_never_converts(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("INTRADAY_EURUSD", "1.1")
        code = self.run(
            monkeypatch,
            tmp_path,
            "--entry",
            "155",
            "--stop",
            "148.5",
            "--account-size",
            "100000",
            "--risk-pct",
            "1",
        )
        assert code in (0, None)
        doc, md = self.read_report(tmp_path)
        assert "fx" not in doc
        assert "€" not in capsys.readouterr().out and "€" not in md

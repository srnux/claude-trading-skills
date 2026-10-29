"""swing-opportunity-daily must check news and earnings before a setup is validated."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "workflows" / "swing-opportunity-daily.yaml"
COMMAND = ROOT / "commands" / "swing.md"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_validation_step_requires_catalyst_and_earnings_check() -> None:
    step = next(s for s in _workflow()["steps"] if s["skill"] == "technical-analyst")
    question = step["decision_question"]

    assert "Catalyst & Event Check" in question
    assert "earnings" in question
    assert "Catalyst & Event Check" in step["decision_question_ja"]


def test_manual_review_lists_news_check() -> None:
    workflow = _workflow()

    assert any("news search" in item for item in workflow["manual_review"])
    assert len(workflow["manual_review"]) == len(workflow["manual_review_ja"])


def test_swing_command_runs_catalyst_check() -> None:
    text = COMMAND.read_text(encoding="utf-8")

    assert "Catalyst & Event Check" in text

import json
import sys

from web_search_search_config.cli import summarize_search_eval as module


def test_main_summarizes_config_distribution(capsys, monkeypatch, tmp_path):
    config_path = tmp_path / "search_eval_cases.json"
    config_path.write_text(
        json.dumps(
            {
                "known_domains": [],
                "query_keyword_rules": {},
                "query_cases": [
                    {
                        "query": "Example comparison",
                        "query_type": "comparison",
                        "expected": "a useful comparison",
                        "notes": "Example local case",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["summarize_search_eval.py", "--config", str(config_path)],
    )

    assert module.main() == 0
    output = capsys.readouterr().out

    assert "Evaluation Set" in output
    assert "search_eval_cases=1" in output
    assert "ignored_duplicates=0" in output
    assert "comparison:" in output


def test_main_summarizes_report_outcomes(capsys, monkeypatch, tmp_path):
    config_path = tmp_path / "search_eval_cases.json"
    report_path = tmp_path / "report.json"
    config_path.write_text(
        json.dumps(
            {
                "known_domains": [],
                "query_keyword_rules": {},
                "query_cases": [],
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "counts": {"matched": 1, "missed": 1},
                "errors": 0,
                "cases": [
                    {"query_type": "reference", "outcome": "matched"},
                    {"query_type": "reference", "outcome": "missed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "summarize_search_eval.py",
            "--config",
            str(config_path),
            "--report",
            str(report_path),
        ],
    )

    assert module.main() == 0
    output = capsys.readouterr().out

    assert "Outcomes" in output
    assert "total_evaluated=2 matched=1 missed=1 match_rate=0.500 errors=0" in output
    assert "reference: total=2 matched=1 missed=1 match_rate=0.500" in output

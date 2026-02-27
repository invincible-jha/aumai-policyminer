"""Tests for aumai-policyminer CLI."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from aumai_policyminer.cli import main


def make_jsonl_content(count: int = 10) -> str:
    lines = []
    for i in range(count):
        log = {
            "log_id": f"l{i:04d}",
            "agent_id": "agent1",
            "action": "approve",
            "context": {"role": "manager"},
            "outcome": "success",
        }
        lines.append(json.dumps(log))
    return "\n".join(lines)


def make_policy_set_json() -> dict:
    return {
        "name": "Test Policies",
        "source_logs": 10,
        "policies": [
            {
                "policy_id": "policy_0001",
                "antecedent": {"role": "manager"},
                "consequent": "approve",
                "support": 0.8,
                "confidence": 0.9,
                "lift": 1.5,
                "description": "When role=manager, agents approve with 90% confidence",
            }
        ],
        "generated_at": "2025-01-01T00:00:00",
    }


class TestCLIVersion:
    def test_cli_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_cli_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0


class TestExtractCommand:
    def test_extract_basic(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("logs.jsonl").write_text(make_jsonl_content(10))
            result = runner.invoke(main, ["extract", "--logs", "logs.jsonl"])
            assert result.exit_code == 0
            assert "Parsed 10 valid log entries" in result.output

    def test_extract_shows_policy_count(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("logs.jsonl").write_text(make_jsonl_content(20))
            result = runner.invoke(main, ["extract", "--logs", "logs.jsonl", "--min-support", "0.01", "--min-confidence", "0.5"])
            assert result.exit_code == 0
            assert "Mined" in result.output

    def test_extract_creates_output_file(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("logs.jsonl").write_text(make_jsonl_content(10))
            result = runner.invoke(main, ["extract", "--logs", "logs.jsonl", "--output", "out.json"])
            assert result.exit_code == 0
            assert Path("out.json").exists()

    def test_extract_output_is_valid_json(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("logs.jsonl").write_text(make_jsonl_content(10))
            runner.invoke(main, ["extract", "--logs", "logs.jsonl", "--output", "out.json", "--min-confidence", "0.5"])
            data = json.loads(Path("out.json").read_text())
            assert "policies" in data
            assert "source_logs" in data

    def test_extract_custom_name(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("logs.jsonl").write_text(make_jsonl_content(10))
            result = runner.invoke(main, ["extract", "--logs", "logs.jsonl", "--name", "My Custom Set"])
            assert result.exit_code == 0
            assert "My Custom Set" in result.output

    def test_extract_missing_logs(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["extract", "--logs", "nonexistent.jsonl"])
        assert result.exit_code != 0

    def test_extract_high_thresholds_zero_policies(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("logs.jsonl").write_text(make_jsonl_content(5))
            result = runner.invoke(main, [
                "extract", "--logs", "logs.jsonl",
                "--min-confidence", "0.99", "--min-lift", "1000.0"
            ])
            assert result.exit_code == 0
            assert "Mined 0 policies" in result.output


class TestFormatCommand:
    def test_format_text(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("policies.json").write_text(json.dumps(make_policy_set_json()))
            result = runner.invoke(main, ["format", "--policies", "policies.json"])
            assert result.exit_code == 0
            assert "Test Policies" in result.output

    def test_format_markdown(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("policies.json").write_text(json.dumps(make_policy_set_json()))
            result = runner.invoke(main, ["format", "--policies", "policies.json", "--output-format", "markdown"])
            assert result.exit_code == 0
            assert "# Test Policies" in result.output

    def test_format_json(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("policies.json").write_text(json.dumps(make_policy_set_json()))
            result = runner.invoke(main, ["format", "--policies", "policies.json", "--output-format", "json"])
            assert result.exit_code == 0
            # Output should be parseable JSON
            output_data = json.loads(result.output)
            assert output_data["name"] == "Test Policies"

    def test_format_missing_file(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["format", "--policies", "nonexistent.json"])
        assert result.exit_code != 0

    def test_format_invalid_json(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("bad.json").write_text("NOT VALID JSON")
            result = runner.invoke(main, ["format", "--policies", "bad.json"])
            assert result.exit_code != 0

    def test_format_max_policies(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            ps = make_policy_set_json()
            # Add extra policies
            ps["policies"] = ps["policies"] * 10
            Path("policies.json").write_text(json.dumps(ps))
            result = runner.invoke(main, ["format", "--policies", "policies.json", "--max-policies", "2"])
            assert result.exit_code == 0

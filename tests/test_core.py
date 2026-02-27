"""Comprehensive tests for aumai-policyminer core module.

Covers:
- LogParser: parse_file, parse_list
- PolicyExtractor: extract with various thresholds
- PolicyFormatter: to_text, to_markdown, to_json_file
- Models: BehaviorLog, MinedPolicy, PolicySet
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aumai_policyminer.core import LogParser, PolicyExtractor, PolicyFormatter
from aumai_policyminer.models import BehaviorLog, MinedPolicy, PolicySet


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_log(
    log_id: str = "log001",
    agent_id: str = "agent_alpha",
    action: str = "read_file",
    context: dict | None = None,
    outcome: str = "success",
) -> BehaviorLog:
    return BehaviorLog(
        log_id=log_id,
        agent_id=agent_id,
        action=action,
        context=context or {"role": "admin", "env": "prod"},
        outcome=outcome,
    )


def make_policy(
    policy_id: str = "policy_0001",
    antecedent: dict | None = None,
    consequent: str = "read_file",
    support: float = 0.3,
    confidence: float = 0.9,
    lift: float = 1.5,
) -> MinedPolicy:
    return MinedPolicy(
        policy_id=policy_id,
        antecedent=antecedent or {"role": "admin"},
        consequent=consequent,
        support=support,
        confidence=confidence,
        lift=lift,
        description=f"When role=admin, agents perform '{consequent}' with 90.0% confidence",
    )


def make_logs_with_pattern(count: int = 10) -> list[BehaviorLog]:
    """Create logs where admin users always read_file."""
    logs: list[BehaviorLog] = []
    for i in range(count):
        logs.append(BehaviorLog(
            log_id=f"log{i:04d}",
            agent_id="agent_alpha",
            action="read_file",
            context={"role": "admin"},
            outcome="success",
        ))
    return logs


# ---------------------------------------------------------------------------
# BehaviorLog model tests
# ---------------------------------------------------------------------------


class TestBehaviorLogModel:
    def test_basic_creation(self) -> None:
        log = make_log()
        assert log.log_id == "log001"
        assert log.agent_id == "agent_alpha"
        assert log.action == "read_file"

    def test_blank_action_raises(self) -> None:
        with pytest.raises(ValidationError):
            BehaviorLog(log_id="l1", agent_id="a1", action="  ")

    def test_blank_agent_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            BehaviorLog(log_id="l1", agent_id="", action="read")

    def test_blank_log_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            BehaviorLog(log_id="", agent_id="agent1", action="read")

    def test_action_stripped(self) -> None:
        log = BehaviorLog(log_id="l1", agent_id="a1", action="  read_file  ")
        assert log.action == "read_file"

    def test_default_outcome_is_success(self) -> None:
        log = make_log()
        assert log.outcome == "success"

    def test_context_defaults_empty(self) -> None:
        log = BehaviorLog(log_id="l1", agent_id="a1", action="read")
        assert log.context == {}

    def test_context_accepts_various_value_types(self) -> None:
        log = BehaviorLog(
            log_id="l1",
            agent_id="a1",
            action="write",
            context={"count": 5, "flag": True, "name": "alice"},
        )
        assert log.context["count"] == 5

    def test_timestamp_is_set(self) -> None:
        log = make_log()
        assert log.timestamp != ""


# ---------------------------------------------------------------------------
# MinedPolicy model tests
# ---------------------------------------------------------------------------


class TestMinedPolicyModel:
    def test_basic_creation(self) -> None:
        policy = make_policy()
        assert policy.policy_id == "policy_0001"
        assert policy.consequent == "read_file"

    def test_support_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MinedPolicy(policy_id="p1", antecedent={}, consequent="read", support=1.1, confidence=0.5)
        with pytest.raises(ValidationError):
            MinedPolicy(policy_id="p1", antecedent={}, consequent="read", support=-0.1, confidence=0.5)

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MinedPolicy(policy_id="p1", antecedent={}, consequent="read", support=0.5, confidence=1.1)

    def test_lift_cannot_be_negative(self) -> None:
        with pytest.raises(ValidationError):
            MinedPolicy(policy_id="p1", antecedent={}, consequent="read", support=0.5, confidence=0.5, lift=-0.1)

    def test_description_defaults_empty(self) -> None:
        policy = MinedPolicy(policy_id="p1", antecedent={}, consequent="read", support=0.5, confidence=0.5)
        assert policy.description == ""


# ---------------------------------------------------------------------------
# PolicySet model tests
# ---------------------------------------------------------------------------


class TestPolicySetModel:
    def test_default_name(self) -> None:
        ps = PolicySet()
        assert ps.name == "Mined Policy Set"

    def test_source_logs_cannot_be_negative(self) -> None:
        with pytest.raises(ValidationError):
            PolicySet(source_logs=-1)

    def test_top_policies_sorted(self) -> None:
        ps = PolicySet(policies=[
            make_policy(policy_id="p1", confidence=0.5),
            make_policy(policy_id="p2", confidence=0.9),
            make_policy(policy_id="p3", confidence=0.7),
        ])
        top = ps.top_policies(2)
        assert len(top) == 2
        assert top[0].confidence >= top[1].confidence

    def test_top_policies_limits_n(self) -> None:
        ps = PolicySet(policies=[make_policy(policy_id=f"p{i}") for i in range(20)])
        top = ps.top_policies(5)
        assert len(top) == 5

    def test_top_policies_returns_all_when_fewer(self) -> None:
        ps = PolicySet(policies=[make_policy()])
        top = ps.top_policies(10)
        assert len(top) == 1

    def test_generated_at_is_set(self) -> None:
        ps = PolicySet()
        assert ps.generated_at != ""


# ---------------------------------------------------------------------------
# LogParser tests
# ---------------------------------------------------------------------------


class TestLogParser:
    def test_parse_list_valid(self) -> None:
        parser = LogParser()
        records = [
            {"log_id": "l1", "agent_id": "a1", "action": "read"},
            {"log_id": "l2", "agent_id": "a2", "action": "write"},
        ]
        logs = parser.parse_list(records)
        assert len(logs) == 2

    def test_parse_list_skips_invalid(self) -> None:
        parser = LogParser()
        records = [
            {"log_id": "l1", "agent_id": "a1", "action": "read"},
            {"invalid": "data_without_required_fields"},
            {"log_id": "l3", "agent_id": "a3", "action": "delete"},
        ]
        logs = parser.parse_list(records)
        assert len(logs) == 2

    def test_parse_list_empty(self) -> None:
        parser = LogParser()
        logs = parser.parse_list([])
        assert logs == []

    def test_parse_file_valid_jsonl(self, tmp_path: Path) -> None:
        parser = LogParser()
        jsonl_path = tmp_path / "logs.jsonl"
        lines = [
            json.dumps({"log_id": "l1", "agent_id": "a1", "action": "read"}),
            json.dumps({"log_id": "l2", "agent_id": "a2", "action": "write"}),
        ]
        jsonl_path.write_text("\n".join(lines), encoding="utf-8")
        logs = parser.parse_file(jsonl_path)
        assert len(logs) == 2

    def test_parse_file_skips_malformed_lines(self, tmp_path: Path) -> None:
        parser = LogParser()
        jsonl_path = tmp_path / "logs.jsonl"
        jsonl_path.write_text(
            json.dumps({"log_id": "l1", "agent_id": "a1", "action": "read"}) + "\n"
            + "NOT VALID JSON\n"
            + json.dumps({"log_id": "l2", "agent_id": "a2", "action": "write"}),
            encoding="utf-8",
        )
        logs = parser.parse_file(jsonl_path)
        assert len(logs) == 2

    def test_parse_file_skips_blank_lines(self, tmp_path: Path) -> None:
        parser = LogParser()
        jsonl_path = tmp_path / "logs.jsonl"
        jsonl_path.write_text(
            json.dumps({"log_id": "l1", "agent_id": "a1", "action": "read"}) + "\n\n",
            encoding="utf-8",
        )
        logs = parser.parse_file(jsonl_path)
        assert len(logs) == 1

    def test_parse_file_empty(self, tmp_path: Path) -> None:
        parser = LogParser()
        jsonl_path = tmp_path / "empty.jsonl"
        jsonl_path.write_text("", encoding="utf-8")
        logs = parser.parse_file(jsonl_path)
        assert logs == []

    def test_parse_list_context_preserved(self) -> None:
        parser = LogParser()
        records = [{"log_id": "l1", "agent_id": "a1", "action": "read", "context": {"role": "admin"}}]
        logs = parser.parse_list(records)
        assert logs[0].context["role"] == "admin"


# ---------------------------------------------------------------------------
# PolicyExtractor tests
# ---------------------------------------------------------------------------


class TestPolicyExtractor:
    def test_extract_empty_logs(self) -> None:
        extractor = PolicyExtractor()
        result = extractor.extract([])
        assert result.source_logs == 0
        assert result.policies == []

    def test_extract_discovers_perfect_pattern(self) -> None:
        logs = make_logs_with_pattern(10)
        extractor = PolicyExtractor(min_support=0.05, min_confidence=0.5, min_lift=1.0)
        result = extractor.extract(logs)
        assert len(result.policies) > 0

    def test_extract_source_logs_count(self) -> None:
        logs = make_logs_with_pattern(10)
        extractor = PolicyExtractor(min_support=0.05, min_confidence=0.5)
        result = extractor.extract(logs)
        assert result.source_logs == 10

    def test_extract_sorted_by_confidence_descending(self) -> None:
        logs: list[BehaviorLog] = []
        for i in range(10):
            logs.append(BehaviorLog(log_id=f"l{i}", agent_id="a1", action="read",
                                     context={"role": "admin"}, outcome="success"))
        for i in range(5):
            logs.append(BehaviorLog(log_id=f"m{i}", agent_id="a2", action="write",
                                     context={"role": "editor"}, outcome="success"))
        extractor = PolicyExtractor(min_support=0.05, min_confidence=0.3, min_lift=1.0)
        result = extractor.extract(logs)
        confidences = [p.confidence for p in result.policies]
        assert confidences == sorted(confidences, reverse=True)

    def test_extract_high_support_threshold_filters(self) -> None:
        # 3 out of 10 logs have role=editor
        logs: list[BehaviorLog] = []
        for i in range(7):
            logs.append(BehaviorLog(log_id=f"l{i}", agent_id="a1", action="read",
                                     context={"role": "admin"}, outcome="success"))
        for i in range(3):
            logs.append(BehaviorLog(log_id=f"m{i}", agent_id="a2", action="write",
                                     context={"role": "editor"}, outcome="success"))
        # Require support > 0.4 (40%) — only admin read_file at 70% should pass
        extractor = PolicyExtractor(min_support=0.4, min_confidence=0.5)
        result = extractor.extract(logs)
        assert all(p.support >= 0.4 for p in result.policies)

    def test_extract_high_confidence_threshold_filters(self) -> None:
        # Mix of admin actions
        logs: list[BehaviorLog] = []
        for i in range(8):
            logs.append(BehaviorLog(log_id=f"l{i}", agent_id="a1", action="read",
                                     context={"role": "admin"}, outcome="success"))
        for i in range(2):
            logs.append(BehaviorLog(log_id=f"m{i}", agent_id="a1", action="write",
                                     context={"role": "admin"}, outcome="success"))
        # Require 90%+ confidence — only read_file from admin (80%) fails this threshold
        extractor = PolicyExtractor(min_support=0.01, min_confidence=0.9)
        result = extractor.extract(logs)
        for policy in result.policies:
            assert policy.confidence >= 0.9

    def test_extract_policy_has_required_fields(self) -> None:
        logs = make_logs_with_pattern(10)
        extractor = PolicyExtractor(min_support=0.05, min_confidence=0.5)
        result = extractor.extract(logs)
        if result.policies:
            policy = result.policies[0]
            assert policy.policy_id.startswith("policy_")
            assert isinstance(policy.antecedent, dict)
            assert isinstance(policy.consequent, str)
            assert 0.0 <= policy.support <= 1.0
            assert 0.0 <= policy.confidence <= 1.0
            assert policy.lift >= 0.0

    def test_extract_custom_name(self) -> None:
        extractor = PolicyExtractor()
        result = extractor.extract([], name="Custom Policy Set")
        assert result.name == "Custom Policy Set"

    def test_extract_lift_above_one_for_strong_patterns(self) -> None:
        # Create a scenario where lift > 1 is expected
        logs = make_logs_with_pattern(20)
        extractor = PolicyExtractor(min_support=0.01, min_confidence=0.5, min_lift=1.0)
        result = extractor.extract(logs)
        for policy in result.policies:
            assert policy.lift >= 1.0

    def test_extract_min_lift_filters_low_lift(self) -> None:
        logs = make_logs_with_pattern(10)
        extractor = PolicyExtractor(min_support=0.01, min_confidence=0.01, min_lift=100.0)
        result = extractor.extract(logs)
        # Lift of 100 is impossible to achieve normally, so all policies filtered
        assert len(result.policies) == 0

    def test_extract_description_contains_confidence_info(self) -> None:
        logs = make_logs_with_pattern(10)
        extractor = PolicyExtractor(min_support=0.01, min_confidence=0.5)
        result = extractor.extract(logs)
        if result.policies:
            assert "confidence" in result.policies[0].description.lower()

    def test_extract_multiple_context_keys(self) -> None:
        logs: list[BehaviorLog] = []
        for i in range(10):
            logs.append(BehaviorLog(
                log_id=f"l{i}",
                agent_id="a1",
                action="delete",
                context={"role": "admin", "env": "prod"},
                outcome="success",
            ))
        extractor = PolicyExtractor(min_support=0.01, min_confidence=0.5)
        result = extractor.extract(logs)
        # Each (key, value) pair creates a separate antecedent
        antecedent_keys = set()
        for policy in result.policies:
            antecedent_keys.update(policy.antecedent.keys())
        assert "role" in antecedent_keys or "env" in antecedent_keys

    def test_extractor_default_thresholds(self) -> None:
        extractor = PolicyExtractor()
        assert extractor.min_support == 0.05
        assert extractor.min_confidence == 0.6
        assert extractor.min_lift == 1.0


# ---------------------------------------------------------------------------
# PolicyFormatter tests
# ---------------------------------------------------------------------------


class TestPolicyFormatter:
    def test_to_text_contains_name(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(name="Test Set", source_logs=100)
        text = formatter.to_text(ps)
        assert "Test Set" in text

    def test_to_text_contains_source_logs(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(name="Test", source_logs=42)
        text = formatter.to_text(ps)
        assert "42" in text

    def test_to_text_contains_total_policies(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(source_logs=10, policies=[make_policy()])
        text = formatter.to_text(ps)
        assert "1" in text

    def test_to_text_policy_details(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(source_logs=10, policies=[make_policy(policy_id="policy_0001")])
        text = formatter.to_text(ps)
        assert "policy_0001" in text

    def test_to_text_max_policies_limits(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(
            source_logs=100,
            policies=[make_policy(policy_id=f"policy_{i:04d}") for i in range(20)],
        )
        text = formatter.to_text(ps, max_policies=5)
        # Only 5 policy IDs should appear in policy lines
        policy_lines = [line for line in text.split("\n") if "policy_" in line and "support=" in line.lower().replace("support=", "X")]
        # Check that we don't have more than 5 policies rendered
        policy_id_lines = [line for line in text.split("\n") if line.startswith("[policy_")]
        assert len(policy_id_lines) <= 5

    def test_to_markdown_contains_header(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(name="My Policies", source_logs=50)
        md = formatter.to_markdown(ps)
        assert "# My Policies" in md

    def test_to_markdown_contains_table_header(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(source_logs=10)
        md = formatter.to_markdown(ps)
        assert "| ID |" in md
        assert "Antecedent" in md
        assert "Consequent" in md

    def test_to_markdown_policy_row(self) -> None:
        formatter = PolicyFormatter()
        policy = make_policy(policy_id="policy_0001", consequent="read_file")
        ps = PolicySet(source_logs=10, policies=[policy])
        md = formatter.to_markdown(ps)
        assert "policy_0001" in md
        assert "read_file" in md

    def test_to_markdown_antecedent_formatted(self) -> None:
        formatter = PolicyFormatter()
        policy = make_policy(antecedent={"role": "admin"})
        ps = PolicySet(source_logs=10, policies=[policy])
        md = formatter.to_markdown(ps)
        assert "role=admin" in md

    def test_to_markdown_max_policies(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(
            source_logs=100,
            policies=[make_policy(policy_id=f"policy_{i:04d}") for i in range(20)],
        )
        md = formatter.to_markdown(ps, max_policies=3)
        # Count rows with policy_ prefix (excluding header)
        table_rows = [line for line in md.split("\n") if line.startswith("| policy_")]
        assert len(table_rows) <= 3

    def test_to_json_file(self, tmp_path: Path) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(name="Test", source_logs=10, policies=[make_policy()])
        output_path = tmp_path / "policies.json"
        formatter.to_json_file(ps, output_path)
        assert output_path.exists()
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["name"] == "Test"
        assert data["source_logs"] == 10
        assert len(data["policies"]) == 1

    def test_to_json_file_valid_policysets_are_loadable(self, tmp_path: Path) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(name="Load Test", source_logs=5, policies=[make_policy()])
        output_path = tmp_path / "load_test.json"
        formatter.to_json_file(ps, output_path)
        data = json.loads(output_path.read_text(encoding="utf-8"))
        loaded = PolicySet.model_validate(data)
        assert loaded.name == "Load Test"

    def test_to_text_empty_policies(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(name="Empty", source_logs=0, policies=[])
        text = formatter.to_text(ps)
        assert "Empty" in text
        assert "0" in text

    def test_to_markdown_source_logs_shown(self) -> None:
        formatter = PolicyFormatter()
        ps = PolicySet(name="Test", source_logs=999)
        md = formatter.to_markdown(ps)
        assert "999" in md

    def test_to_text_includes_support_confidence_lift(self) -> None:
        formatter = PolicyFormatter()
        policy = make_policy(support=0.3, confidence=0.9, lift=1.5)
        ps = PolicySet(source_logs=10, policies=[policy])
        text = formatter.to_text(ps)
        assert "support=" in text
        assert "confidence=" in text
        assert "lift=" in text


# ---------------------------------------------------------------------------
# Integration: LogParser + PolicyExtractor + PolicyFormatter
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_end_to_end_extract_and_format(self, tmp_path: Path) -> None:
        """Full pipeline: write JSONL, parse, extract, format."""
        # Write JSONL file
        jsonl_path = tmp_path / "behavior.jsonl"
        lines: list[str] = []
        for i in range(20):
            log = {"log_id": f"l{i}", "agent_id": "agent1", "action": "approve",
                   "context": {"role": "manager"}, "outcome": "success"}
            lines.append(json.dumps(log))
        jsonl_path.write_text("\n".join(lines), encoding="utf-8")

        # Parse
        parser = LogParser()
        logs = parser.parse_file(jsonl_path)
        assert len(logs) == 20

        # Extract
        extractor = PolicyExtractor(min_support=0.01, min_confidence=0.5)
        policy_set = extractor.extract(logs, name="Test Integration Set")
        assert policy_set.source_logs == 20
        assert len(policy_set.policies) > 0

        # Format to text
        formatter = PolicyFormatter()
        text = formatter.to_text(policy_set)
        assert "Test Integration Set" in text

        # Format to markdown
        md = formatter.to_markdown(policy_set)
        assert "# Test Integration Set" in md

        # Save and reload
        output_path = tmp_path / "policies.json"
        formatter.to_json_file(policy_set, output_path)
        data = json.loads(output_path.read_text(encoding="utf-8"))
        reloaded = PolicySet.model_validate(data)
        assert reloaded.name == "Test Integration Set"

    def test_parse_list_then_extract(self) -> None:
        parser = LogParser()
        records = [
            {"log_id": f"l{i}", "agent_id": "agent1", "action": "read",
             "context": {"env": "staging"}}
            for i in range(15)
        ]
        logs = parser.parse_list(records)
        extractor = PolicyExtractor(min_support=0.05, min_confidence=0.5)
        result = extractor.extract(logs)
        assert result.source_logs == 15
        assert all(p.support >= 0.05 for p in result.policies)
        assert all(p.confidence >= 0.5 for p in result.policies)

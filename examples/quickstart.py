"""Quickstart examples for aumai-policyminer.

Run this file directly to verify your installation and see the library in action:

    python examples/quickstart.py

This file demonstrates:
  1. Parsing behavior logs from Python dicts
  2. Mining policies with the default extractor
  3. Mining with strict thresholds for high-stakes governance
  4. Rendering policies as text, Markdown, and JSON
  5. Saving and reloading policy sets
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

from aumai_policyminer.core import LogParser, PolicyExtractor, PolicyFormatter
from aumai_policyminer.models import BehaviorLog, PolicySet


# ---------------------------------------------------------------------------
# Helpers: synthetic log generation
# ---------------------------------------------------------------------------


def generate_synthetic_logs(n: int = 200, seed: int = 42) -> list[dict]:
    """Generate n synthetic behavior log records with realistic patterns.

    Patterns baked in:
    - role=admin -> delete_record with ~70% frequency (high lift)
    - role=viewer -> read_file with ~80% frequency
    - role=editor -> write_file with ~60% frequency
    - env=prod -> audit_log with ~40% frequency across all roles
    """
    random.seed(seed)

    role_weights = {"admin": 0.2, "viewer": 0.4, "editor": 0.25, "analyst": 0.15}
    env_weights = {"prod": 0.5, "staging": 0.3, "dev": 0.2}

    action_by_role = {
        "admin":   ["delete_record", "write_file", "read_file", "audit_log", "approve"],
        "viewer":  ["read_file", "read_file", "read_file", "audit_log", "send_email"],
        "editor":  ["write_file", "write_file", "read_file", "audit_log", "send_email"],
        "analyst": ["read_file", "audit_log", "export_data", "send_email", "read_file"],
    }

    records = []
    for i in range(n):
        role = random.choices(list(role_weights), weights=list(role_weights.values()))[0]
        env = random.choices(list(env_weights), weights=list(env_weights.values()))[0]
        action = random.choice(action_by_role[role])
        outcome = random.choices(["success", "denied", "error"], weights=[0.85, 0.1, 0.05])[0]
        records.append({
            "log_id": f"log_{i:04d}",
            "agent_id": f"agent_{random.choice('ABCDE')}",
            "action": action,
            "context": {"role": role, "env": env},
            "outcome": outcome,
        })
    return records


# ---------------------------------------------------------------------------
# Demo 1: Parsing from Python dicts
# ---------------------------------------------------------------------------


def demo_parse_from_dicts() -> None:
    """Parse behavior logs from a list of Python dictionaries.

    Demonstrates:
    - LogParser.parse_list()
    - BehaviorLog field access
    """
    print("=" * 60)
    print("Demo 1: Parsing Behavior Logs from Python Dicts")
    print("=" * 60)

    raw_records = generate_synthetic_logs(n=200)
    parser = LogParser()
    logs: list[BehaviorLog] = parser.parse_list(raw_records)

    print(f"  Parsed {len(logs)} valid log entries.")

    # Summarize by action
    action_counts: dict[str, int] = {}
    for log in logs:
        action_counts[log.action] = action_counts.get(log.action, 0) + 1

    print("\n  Action frequency summary:")
    for action, count in sorted(action_counts.items(), key=lambda x: -x[1]):
        bar = "#" * int(count / 3)
        print(f"    {action:<20} {count:>4}  {bar}")
    print()


# ---------------------------------------------------------------------------
# Demo 2: Mining policies with default thresholds
# ---------------------------------------------------------------------------


def demo_mine_default() -> None:
    """Mine policies using default thresholds.

    Demonstrates:
    - PolicyExtractor with defaults
    - PolicySet.top_policies()
    - PolicyFormatter.to_text()
    """
    print("=" * 60)
    print("Demo 2: Mining Policies (Default Thresholds)")
    print("=" * 60)

    raw_records = generate_synthetic_logs(n=300)
    parser = LogParser()
    logs = parser.parse_list(raw_records)

    extractor = PolicyExtractor(
        min_support=0.05,
        min_confidence=0.5,
        min_lift=1.0,
    )
    policy_set = extractor.extract(logs, name="Default Threshold Policies")

    print(f"  Analyzed {policy_set.source_logs} logs.")
    print(f"  Discovered {len(policy_set.policies)} policies.\n")

    print("  Top 5 policies by confidence:")
    for policy in policy_set.top_policies(5):
        print(f"    [{policy.policy_id}]")
        print(f"      Antecedent: {policy.antecedent}")
        print(f"      Consequent: {policy.consequent}")
        print(f"      Support:    {policy.support:.1%}")
        print(f"      Confidence: {policy.confidence:.1%}")
        print(f"      Lift:       {policy.lift:.2f}")
        print()


# ---------------------------------------------------------------------------
# Demo 3: Strict thresholds for high-stakes governance
# ---------------------------------------------------------------------------


def demo_strict_thresholds() -> None:
    """Mine with strict thresholds to surface only the most reliable patterns.

    Demonstrates:
    - PolicyExtractor with tight min_confidence and min_lift
    - Filtering by action type
    """
    print("=" * 60)
    print("Demo 3: Strict Thresholds (High-Stakes Governance)")
    print("=" * 60)

    raw_records = generate_synthetic_logs(n=500)
    parser = LogParser()
    logs = parser.parse_list(raw_records)

    extractor = PolicyExtractor(
        min_support=0.05,
        min_confidence=0.75,
        min_lift=1.5,
    )
    policy_set = extractor.extract(logs, name="High-Confidence Governance Policies")

    print(f"  Strict extraction: {len(policy_set.policies)} policies "
          f"(from {policy_set.source_logs} logs).")

    # Highlight potentially risky policies (high-confidence delete/approve)
    risky_actions = {"delete_record", "approve"}
    risky_policies = [
        p for p in policy_set.policies if p.consequent in risky_actions
    ]
    if risky_policies:
        print(f"\n  Risky high-confidence policies ({len(risky_policies)}):")
        for p in risky_policies:
            print(f"    RISK: {p.description}")
    else:
        print("\n  No risky high-confidence policies detected.")
    print()


# ---------------------------------------------------------------------------
# Demo 4: Rendering to text, Markdown, and JSON
# ---------------------------------------------------------------------------


def demo_rendering() -> None:
    """Render a policy set in all available output formats.

    Demonstrates:
    - PolicyFormatter.to_text()
    - PolicyFormatter.to_markdown()
    - PolicySet.model_dump_json()
    """
    print("=" * 60)
    print("Demo 4: Rendering Policy Sets")
    print("=" * 60)

    raw_records = generate_synthetic_logs(n=150)
    parser = LogParser()
    logs = parser.parse_list(raw_records)

    extractor = PolicyExtractor(min_support=0.05, min_confidence=0.55)
    policy_set = extractor.extract(logs, name="Rendering Demo")

    formatter = PolicyFormatter()

    # Plain text (show first 3 policies)
    print("  -- Plain Text (max 3 policies) --")
    text_output = formatter.to_text(policy_set, max_policies=3)
    for line in text_output.splitlines():
        print(f"  {line}")

    print("\n  -- Markdown Table (max 3 policies) --")
    md_output = formatter.to_markdown(policy_set, max_policies=3)
    for line in md_output.splitlines():
        print(f"  {line}")
    print()


# ---------------------------------------------------------------------------
# Demo 5: Saving and reloading policy sets
# ---------------------------------------------------------------------------


def demo_save_reload(tmp_dir: Path) -> None:
    """Save a policy set to JSON and reload it for later use.

    Demonstrates:
    - PolicyFormatter.to_json_file()
    - PolicySet.model_validate()
    - PolicySet.top_policies()
    """
    print("=" * 60)
    print("Demo 5: Save and Reload Policy Sets")
    print("=" * 60)

    raw_records = generate_synthetic_logs(n=250)
    parser = LogParser()
    logs = parser.parse_list(raw_records)

    extractor = PolicyExtractor(min_support=0.04, min_confidence=0.5)
    policy_set = extractor.extract(logs, name="Persisted Policy Set v1")

    # Save
    out_path = tmp_dir / "policies_v1.json"
    formatter = PolicyFormatter()
    formatter.to_json_file(policy_set, out_path)
    print(f"  Saved {len(policy_set.policies)} policies to {out_path}")

    # Reload
    data = json.loads(out_path.read_text(encoding="utf-8"))
    loaded: PolicySet = PolicySet.model_validate(data)
    print(f"  Reloaded policy set: '{loaded.name}'")
    print(f"  Source logs: {loaded.source_logs}")
    print(f"  Generated:   {loaded.generated_at}")
    print(f"  Policies:    {len(loaded.policies)}")

    print("\n  Top 3 reloaded policies:")
    for p in loaded.top_policies(3):
        print(f"    {p.policy_id}: conf={p.confidence:.1%}, lift={p.lift:.2f}")
        print(f"      {p.description}")
    print()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all quickstart demos in sequence."""
    print("\naumai-policyminer Quickstart Demos")
    print("=" * 60)
    print()

    demo_parse_from_dicts()
    demo_mine_default()
    demo_strict_thresholds()
    demo_rendering()

    with tempfile.TemporaryDirectory() as tmp:
        demo_save_reload(Path(tmp))

    print("All demos completed successfully.")


if __name__ == "__main__":
    main()

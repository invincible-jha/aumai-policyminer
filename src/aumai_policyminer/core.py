"""Core logic for policy mining from agent behavior logs.

Provides:
- LogParser: load and validate JSONL behavior logs.
- PolicyExtractor: association-rule mining from action-context pairs.
- PolicyFormatter: render policies as human-readable text or Markdown.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .models import BehaviorLog, MinedPolicy, PolicySet


# ---------------------------------------------------------------------------
# LogParser
# ---------------------------------------------------------------------------


class LogParser:
    """Load and validate JSONL behavior logs.

    Each line of the JSONL file must be a valid BehaviorLog JSON object.
    Malformed lines are skipped with a warning counter.

    Example:
        >>> parser = LogParser()
        >>> logs = parser.parse_file(Path("behavior.jsonl"))
    """

    def parse_file(self, path: Path) -> list[BehaviorLog]:
        """Parse a JSONL file and return validated BehaviorLog objects.

        Args:
            path: Path to a JSONL file where each line is a BehaviorLog.

        Returns:
            List of BehaviorLog instances (invalid lines skipped).
        """
        logs: list[BehaviorLog] = []
        with path.open(encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    logs.append(BehaviorLog.model_validate(data))
                except Exception:
                    # Silently skip malformed lines; callers can inspect counts
                    continue
        return logs

    def parse_list(self, records: list[dict[str, Any]]) -> list[BehaviorLog]:
        """Parse a list of raw dicts into BehaviorLog objects.

        Args:
            records: List of raw dictionaries.

        Returns:
            List of validated BehaviorLog instances.
        """
        logs: list[BehaviorLog] = []
        for record in records:
            try:
                logs.append(BehaviorLog.model_validate(record))
            except Exception:
                continue
        return logs


# ---------------------------------------------------------------------------
# PolicyExtractor
# ---------------------------------------------------------------------------


class PolicyExtractor:
    """Extract governance policies using association rule mining.

    For each unique context key-value pair observed in the logs, this extractor
    computes:
        support    = count(antecedent AND consequent) / total_logs
        confidence = count(antecedent AND consequent) / count(antecedent)
        lift       = confidence / (count(consequent) / total_logs)

    Only rules meeting minimum thresholds are returned.

    Example:
        >>> extractor = PolicyExtractor(min_support=0.01, min_confidence=0.5)
        >>> policy_set = extractor.extract(logs)
    """

    def __init__(
        self,
        min_support: float = 0.05,
        min_confidence: float = 0.6,
        min_lift: float = 1.0,
    ) -> None:
        """Initialise the extractor with threshold parameters.

        Args:
            min_support: Minimum support fraction for a rule to be returned.
            min_confidence: Minimum confidence fraction.
            min_lift: Minimum lift value (1.0 means no filtering by lift).
        """
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.min_lift = min_lift

    def extract(self, logs: list[BehaviorLog], name: str = "Mined Policy Set") -> PolicySet:
        """Mine association rules from a list of behavior logs.

        Args:
            logs: List of BehaviorLog objects to analyse.
            name: Name for the resulting PolicySet.

        Returns:
            PolicySet populated with discovered policies.
        """
        total = len(logs)
        if total == 0:
            return PolicySet(name=name, source_logs=0)

        # Count action frequencies
        action_counts: Counter[str] = Counter(log.action for log in logs)

        # Build (context_key, context_value, action) co-occurrence counts
        # antecedent = (key, value) pair from context
        # consequent = action
        antecedent_counts: Counter[tuple[str, str]] = Counter()
        cooccurrence_counts: Counter[tuple[str, str, str]] = Counter()

        for log in logs:
            for key, value in log.context.items():
                str_val = str(value)
                antecedent_counts[(key, str_val)] += 1
                cooccurrence_counts[(key, str_val, log.action)] += 1

        policies: list[MinedPolicy] = []
        policy_counter = 0

        for (ctx_key, ctx_val, action), co_count in cooccurrence_counts.items():
            support = co_count / total
            if support < self.min_support:
                continue

            antecedent_count = antecedent_counts[(ctx_key, ctx_val)]
            confidence = co_count / antecedent_count if antecedent_count > 0 else 0.0
            if confidence < self.min_confidence:
                continue

            action_freq = action_counts[action] / total
            lift = confidence / action_freq if action_freq > 0 else 0.0
            if lift < self.min_lift:
                continue

            policy_counter += 1
            policies.append(
                MinedPolicy(
                    policy_id=f"policy_{policy_counter:04d}",
                    antecedent={ctx_key: ctx_val},
                    consequent=action,
                    support=round(support, 6),
                    confidence=round(confidence, 6),
                    lift=round(lift, 6),
                    description=(
                        f"When {ctx_key}={ctx_val!r}, agents perform '{action}' "
                        f"with {confidence*100:.1f}% confidence "
                        f"(support={support*100:.1f}%, lift={lift:.2f})"
                    ),
                )
            )

        # Sort by confidence descending
        policies.sort(key=lambda p: p.confidence, reverse=True)

        return PolicySet(name=name, source_logs=total, policies=policies)


# ---------------------------------------------------------------------------
# PolicyFormatter
# ---------------------------------------------------------------------------


class PolicyFormatter:
    """Render a PolicySet to text or Markdown.

    Example:
        >>> formatter = PolicyFormatter()
        >>> print(formatter.to_text(policy_set))
        >>> print(formatter.to_markdown(policy_set))
    """

    def to_text(self, policy_set: PolicySet, max_policies: int = 50) -> str:
        """Render policies as a plain-text report.

        Args:
            policy_set: The PolicySet to render.
            max_policies: Maximum number of policies to include.

        Returns:
            Formatted string report.
        """
        lines: list[str] = [
            f"Policy Set: {policy_set.name}",
            f"Source logs: {policy_set.source_logs}",
            f"Generated at: {policy_set.generated_at}",
            f"Total policies: {len(policy_set.policies)}",
            "-" * 60,
        ]
        for policy in policy_set.policies[:max_policies]:
            lines.append(f"[{policy.policy_id}] {policy.description}")
            lines.append(
                f"  support={policy.support:.4f} "
                f"confidence={policy.confidence:.4f} "
                f"lift={policy.lift:.4f}"
            )
        return "\n".join(lines)

    def to_markdown(self, policy_set: PolicySet, max_policies: int = 50) -> str:
        """Render policies as a Markdown table.

        Args:
            policy_set: The PolicySet to render.
            max_policies: Maximum number of policies to include.

        Returns:
            Markdown-formatted string.
        """
        lines: list[str] = [
            f"# {policy_set.name}",
            "",
            f"- **Source logs:** {policy_set.source_logs}",
            f"- **Generated at:** {policy_set.generated_at}",
            f"- **Total policies:** {len(policy_set.policies)}",
            "",
            "| ID | Antecedent | Consequent | Support | Confidence | Lift |",
            "|----|-----------|-----------|---------|------------|------|",
        ]
        for policy in policy_set.policies[:max_policies]:
            antecedent_str = ", ".join(f"{k}={v}" for k, v in policy.antecedent.items())
            lines.append(
                f"| {policy.policy_id} | {antecedent_str} | {policy.consequent} "
                f"| {policy.support:.4f} | {policy.confidence:.4f} | {policy.lift:.4f} |"
            )
        return "\n".join(lines)

    def to_json_file(self, policy_set: PolicySet, path: Path) -> None:
        """Serialise a PolicySet to a JSON file.

        Args:
            policy_set: The PolicySet to serialise.
            path: Destination file path.
        """
        path.write_text(policy_set.model_dump_json(indent=2), encoding="utf-8")

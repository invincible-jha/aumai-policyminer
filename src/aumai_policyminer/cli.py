"""CLI entry point for aumai-policyminer.

Commands:
    extract  -- mine policies from a JSONL behavior log file
    format   -- render a JSON policy set as text or Markdown
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .core import LogParser, PolicyExtractor, PolicyFormatter
from .models import PolicySet


@click.group()
@click.version_option()
def main() -> None:
    """AumAI PolicyMiner -- governance policy extraction CLI."""


@main.command("extract")
@click.option(
    "--logs",
    "logs_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a JSONL behavior log file.",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(path_type=Path),
    help="Output JSON path. Defaults to policies.json in the same directory.",
)
@click.option(
    "--min-support",
    default=0.05,
    show_default=True,
    type=float,
    help="Minimum support threshold (0.0 - 1.0).",
)
@click.option(
    "--min-confidence",
    default=0.6,
    show_default=True,
    type=float,
    help="Minimum confidence threshold (0.0 - 1.0).",
)
@click.option(
    "--min-lift",
    default=1.0,
    show_default=True,
    type=float,
    help="Minimum lift threshold.",
)
@click.option("--name", default="Mined Policy Set", show_default=True, type=str)
def extract_command(
    logs_path: Path,
    output_path: Path | None,
    min_support: float,
    min_confidence: float,
    min_lift: float,
    name: str,
) -> None:
    """Extract governance policies from a JSONL behavior log file.

    Example:

        aumai-policyminer extract --logs behavior.jsonl --min-confidence 0.7
    """
    parser = LogParser()
    logs = parser.parse_file(logs_path)
    click.echo(f"Parsed {len(logs)} valid log entries.")

    extractor = PolicyExtractor(
        min_support=min_support,
        min_confidence=min_confidence,
        min_lift=min_lift,
    )
    policy_set = extractor.extract(logs, name=name)
    click.echo(f"Mined {len(policy_set.policies)} policies.")

    formatter = PolicyFormatter()
    dest = output_path or logs_path.parent / "policies.json"
    formatter.to_json_file(policy_set, dest)
    click.echo(f"Saved policy set to {dest}")

    # Print a brief summary
    click.echo(formatter.to_text(policy_set, max_policies=10))


@main.command("format")
@click.option(
    "--policies",
    "policies_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a JSON policies file.",
)
@click.option(
    "--output-format",
    "output_format",
    default="text",
    show_default=True,
    type=click.Choice(["text", "markdown", "json"], case_sensitive=False),
    help="Output format.",
)
@click.option(
    "--max-policies",
    default=50,
    show_default=True,
    type=int,
    help="Maximum number of policies to render.",
)
def format_command(
    policies_path: Path, output_format: str, max_policies: int
) -> None:
    """Render a JSON policy set as text, Markdown, or JSON.

    Example:

        aumai-policyminer format --policies policies.json --output-format markdown
    """
    try:
        data = json.loads(policies_path.read_text(encoding="utf-8"))
        policy_set = PolicySet.model_validate(data)
    except Exception as exc:
        click.echo(f"ERROR loading policy set: {exc}", err=True)
        sys.exit(1)

    formatter = PolicyFormatter()

    if output_format == "text":
        click.echo(formatter.to_text(policy_set, max_policies=max_policies))
    elif output_format == "markdown":
        click.echo(formatter.to_markdown(policy_set, max_policies=max_policies))
    else:
        click.echo(policy_set.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

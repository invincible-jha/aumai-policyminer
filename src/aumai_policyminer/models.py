"""Pydantic v2 models for the policy miner."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class BehaviorLog(BaseModel):
    """A single recorded agent action in context.

    Attributes:
        log_id: Unique identifier for the log entry.
        agent_id: Identifier of the agent that performed the action.
        timestamp: ISO-8601 datetime string of the event.
        action: The action the agent took (e.g. "read_file", "send_email").
        context: Key-value metadata describing the situation when action occurred.
        outcome: Optional outcome label (e.g. "success", "denied", "error").
    """

    log_id: str
    agent_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    action: str
    context: dict[str, Any] = Field(default_factory=dict)
    outcome: str = Field(default="success")

    @field_validator("action", "agent_id", "log_id")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        """Ensure critical string fields are not blank."""
        if not value.strip():
            raise ValueError("Field must not be blank.")
        return value.strip()


class MinedPolicy(BaseModel):
    """A governance policy extracted from behavioral patterns.

    Attributes:
        policy_id: Unique identifier for the policy.
        antecedent: The triggering context pattern (e.g. {"role": "admin"}).
        consequent: The action pattern associated with this context.
        support: Fraction of logs that contain this pattern (0 to 1).
        confidence: Fraction of antecedent occurrences that show the consequent.
        lift: Ratio of observed confidence to baseline action frequency.
        description: Human-readable explanation of the policy.
    """

    policy_id: str
    antecedent: dict[str, Any]
    consequent: str
    support: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    lift: float = Field(default=1.0, ge=0.0)
    description: str = Field(default="")


class PolicySet(BaseModel):
    """A collection of mined policies with metadata.

    Attributes:
        name: Human-readable name for this policy set.
        source_logs: Number of logs analysed.
        policies: List of mined policies sorted by confidence descending.
        generated_at: ISO-8601 timestamp when the set was generated.
    """

    name: str = Field(default="Mined Policy Set")
    source_logs: int = Field(default=0, ge=0)
    policies: list[MinedPolicy] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def top_policies(self, n: int = 10) -> list[MinedPolicy]:
        """Return the top-n policies sorted by confidence descending.

        Args:
            n: Maximum number of policies to return.

        Returns:
            List of MinedPolicy objects.
        """
        return sorted(self.policies, key=lambda p: p.confidence, reverse=True)[:n]

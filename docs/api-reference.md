# API Reference — aumai-policyminer

Complete reference for all public classes, methods, and Pydantic models in
`aumai_policyminer`. All classes are importable from their module paths shown
below.

---

## Module: `aumai_policyminer.models`

### `BehaviorLog`

```python
class BehaviorLog(BaseModel):
```

A single recorded agent action in context. This is the fundamental unit of
data ingested by the policy miner.

**Fields:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `log_id` | `str` | Yes | — | Unique identifier for the log entry |
| `agent_id` | `str` | Yes | — | Identifier of the agent that performed the action |
| `timestamp` | `str` | No | `datetime.now(UTC).isoformat()` | ISO-8601 datetime string of the event |
| `action` | `str` | Yes | — | The action the agent took (e.g. `"read_file"`, `"send_email"`) |
| `context` | `dict[str, Any]` | No | `{}` | Key-value metadata describing the situation when the action occurred |
| `outcome` | `str` | No | `"success"` | Optional outcome label (e.g. `"success"`, `"denied"`, `"error"`) |

**Validators:**

- `must_not_be_blank`: applied to `log_id`, `agent_id`, and `action` — raises
  `ValueError` if any of these are blank or whitespace-only strings

**Example:**

```python
from aumai_policyminer.models import BehaviorLog

log = BehaviorLog(
    log_id="l001",
    agent_id="agent_A",
    action="read_file",
    context={"role": "admin", "env": "prod", "sensitivity": "high"},
    outcome="success",
)
```

**JSON schema (for JSONL log files):**

```json
{
  "log_id": "l001",
  "agent_id": "agent_A",
  "timestamp": "2025-01-15T10:30:00+00:00",
  "action": "read_file",
  "context": {"role": "admin", "env": "prod"},
  "outcome": "success"
}
```

---

### `MinedPolicy`

```python
class MinedPolicy(BaseModel):
```

A governance policy extracted from behavioral patterns via association rule
mining.

**Fields:**

| Field | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `policy_id` | `str` | Yes | — | — | Auto-assigned unique identifier (e.g. `"policy_0001"`) |
| `antecedent` | `dict[str, Any]` | Yes | — | — | The triggering context pattern, e.g. `{"role": "admin"}` |
| `consequent` | `str` | Yes | — | — | The action pattern associated with this context |
| `support` | `float` | Yes | — | `ge=0.0, le=1.0` | Fraction of logs that contain this pattern |
| `confidence` | `float` | Yes | — | `ge=0.0, le=1.0` | Fraction of antecedent occurrences that show the consequent |
| `lift` | `float` | No | `1.0` | `ge=0.0` | Ratio of observed confidence to baseline action frequency |
| `description` | `str` | No | `""` | — | Auto-generated human-readable explanation |

**Metric definitions:**

- `support = count(antecedent AND consequent) / total_logs`
- `confidence = count(antecedent AND consequent) / count(antecedent)`
- `lift = confidence / (count(consequent) / total_logs)`

**Example:**

```python
from aumai_policyminer.models import MinedPolicy

policy = MinedPolicy(
    policy_id="policy_0001",
    antecedent={"role": "admin"},
    consequent="delete_record",
    support=0.12,
    confidence=0.87,
    lift=3.4,
    description="When role='admin', agents perform 'delete_record' with 87.0% confidence",
)
```

---

### `PolicySet`

```python
class PolicySet(BaseModel):
```

A collection of mined policies with metadata.

**Fields:**

| Field | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `name` | `str` | No | `"Mined Policy Set"` | — | Human-readable name for this policy set |
| `source_logs` | `int` | No | `0` | `ge=0` | Number of logs analysed |
| `policies` | `list[MinedPolicy]` | No | `[]` | — | List of mined policies sorted by confidence descending |
| `generated_at` | `str` | No | `datetime.now(UTC).isoformat()` | — | ISO-8601 timestamp when the set was generated |

**Methods:**

#### `top_policies(n: int = 10) -> list[MinedPolicy]`

Return the top-n policies sorted by confidence descending.

**Parameters:**
- `n` — maximum number of policies to return (default: 10)

**Returns:**
- `list[MinedPolicy]` — at most `n` policies, highest confidence first

**Example:**

```python
for policy in policy_set.top_policies(5):
    print(f"{policy.policy_id}: conf={policy.confidence:.2%}")
```

---

## Module: `aumai_policyminer.core`

### `LogParser`

```python
class LogParser:
```

Load and validate JSONL behavior logs. Each line of the JSONL file must be a
valid `BehaviorLog` JSON object. Malformed lines are skipped silently.

#### `parse_file(path: Path) -> list[BehaviorLog]`

Parse a JSONL file and return validated `BehaviorLog` objects.

**Parameters:**
- `path` — `pathlib.Path` to a JSONL file where each line is a `BehaviorLog`

**Returns:**
- `list[BehaviorLog]` — validated instances; invalid lines are skipped

**Side effect:**
- Sets `self.skipped_count: int` to the number of skipped malformed lines

**Example:**

```python
from pathlib import Path
from aumai_policyminer.core import LogParser

parser = LogParser()
logs = parser.parse_file(Path("agent_logs.jsonl"))
print(f"Loaded: {len(logs)}, Skipped: {parser.skipped_count}")
```

#### `parse_list(records: list[dict[str, Any]]) -> list[BehaviorLog]`

Parse a list of raw dictionaries into `BehaviorLog` objects.

**Parameters:**
- `records` — list of raw dictionaries

**Returns:**
- `list[BehaviorLog]` — validated instances; invalid dicts are skipped silently

**Example:**

```python
parser = LogParser()
logs = parser.parse_list([
    {"log_id": "l1", "agent_id": "A", "action": "read"},
    {"log_id": "l2", "agent_id": "B", "action": "write"},
])
```

---

### `PolicyExtractor`

```python
class PolicyExtractor:
```

Extract governance policies using association rule mining.

For each unique `(context_key, context_value, action)` triple observed in the
logs, computes support, confidence, and lift. Only rules meeting all minimum
thresholds are returned.

#### `__init__(min_support: float = 0.05, min_confidence: float = 0.6, min_lift: float = 1.0) -> None`

Initialise the extractor with threshold parameters.

**Parameters:**
- `min_support` — minimum support fraction for a rule to be returned
  (default: `0.05`)
- `min_confidence` — minimum confidence fraction (default: `0.6`)
- `min_lift` — minimum lift value; `1.0` means no filtering by lift
  (default: `1.0`)

**Example:**

```python
from aumai_policyminer.core import PolicyExtractor

extractor = PolicyExtractor(
    min_support=0.03,
    min_confidence=0.75,
    min_lift=1.5,
)
```

#### `extract(logs: list[BehaviorLog], name: str = "Mined Policy Set") -> PolicySet`

Mine association rules from a list of behavior logs.

**Parameters:**
- `logs` — list of `BehaviorLog` objects to analyse
- `name` — human-readable name for the resulting `PolicySet` (default:
  `"Mined Policy Set"`)

**Returns:**
- `PolicySet` populated with discovered policies, sorted by confidence
  descending

**Notes:**
- Returns an empty `PolicySet` (with `source_logs=0`) if `logs` is empty.
- Policy IDs are auto-assigned as `"policy_0001"`, `"policy_0002"`, etc.

**Example:**

```python
from pathlib import Path
from aumai_policyminer.core import LogParser, PolicyExtractor

parser = LogParser()
logs = parser.parse_file(Path("logs.jsonl"))

extractor = PolicyExtractor(min_confidence=0.7)
policy_set = extractor.extract(logs, name="Agent Governance v1")
print(f"Mined {len(policy_set.policies)} policies")
```

---

### `PolicyFormatter`

```python
class PolicyFormatter:
```

Render a `PolicySet` to text, Markdown, or JSON.

#### `to_text(policy_set: PolicySet, max_policies: int = 50) -> str`

Render policies as a plain-text report.

**Parameters:**
- `policy_set` — the `PolicySet` to render
- `max_policies` — maximum number of policies to include (default: `50`)

**Returns:**
- Formatted string with header lines (name, source logs, generated at, total
  policies) followed by one paragraph per policy

**Example:**

```python
from aumai_policyminer.core import PolicyFormatter

formatter = PolicyFormatter()
print(formatter.to_text(policy_set, max_policies=20))
```

#### `to_markdown(policy_set: PolicySet, max_policies: int = 50) -> str`

Render policies as a Markdown table.

**Parameters:**
- `policy_set` — the `PolicySet` to render
- `max_policies` — maximum number of policies to include (default: `50`)

**Returns:**
- Markdown-formatted string with a header, metadata bullet list, and a table
  with columns: ID, Antecedent, Consequent, Support, Confidence, Lift

**Example:**

```python
markdown = formatter.to_markdown(policy_set)
# | ID | Antecedent | Consequent | Support | Confidence | Lift |
# | policy_0001 | role=admin | delete_record | 0.1200 | 0.8700 | 3.4000 |
```

#### `to_json_file(policy_set: PolicySet, path: Path) -> None`

Serialise a `PolicySet` to a JSON file.

**Parameters:**
- `policy_set` — the `PolicySet` to serialise
- `path` — destination `pathlib.Path`

**Example:**

```python
from pathlib import Path

formatter.to_json_file(policy_set, Path("policies_v1.json"))
```

---

## Module: `aumai_policyminer.cli`

### `main`

CLI entry point registered as `aumai-policyminer`.

| Command | Description |
|---|---|
| `extract` | Mine policies from a JSONL behavior log file |
| `format` | Render a JSON policy set as text, Markdown, or JSON |

See [README.md](../README.md) for full CLI usage with examples.

---

## Package-level exports

`aumai_policyminer.__version__` — current version string (`"0.1.0"`).

Import directly from submodules:

```python
from aumai_policyminer.core import LogParser, PolicyExtractor, PolicyFormatter
from aumai_policyminer.models import BehaviorLog, MinedPolicy, PolicySet
```

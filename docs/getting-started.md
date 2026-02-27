# Getting Started with aumai-policyminer

This guide takes you from zero to extracting governance policies from real
agent behavior logs in under 15 minutes.

---

## Prerequisites

- Python 3.11 or higher
- `pip` (standard) or `uv` (recommended)
- Agent behavior logs in JSONL format, or the ability to generate synthetic
  ones (the tutorial shows how)

---

## Installation

### From PyPI (stable)

```bash
pip install aumai-policyminer
```

### From source (development)

```bash
git clone https://github.com/AumAI/aumai-policyminer
cd aumai-policyminer
pip install -e ".[dev]"
```

### Verify the installation

```bash
aumai-policyminer --version
# aumai-policyminer, version 0.1.0

python -c "import aumai_policyminer; print('OK')"
# OK
```

---

## Step-by-Step Tutorial

### Step 1: Create a sample behavior log

If you don't have logs yet, create a `sample_logs.jsonl` file. Each line must
be a JSON object:

```jsonl
{"log_id": "l001", "agent_id": "agent_A", "action": "read_file", "context": {"role": "admin", "env": "prod"}, "outcome": "success"}
{"log_id": "l002", "agent_id": "agent_A", "action": "read_file", "context": {"role": "admin", "env": "prod"}, "outcome": "success"}
{"log_id": "l003", "agent_id": "agent_B", "action": "send_email", "context": {"role": "user", "env": "staging"}, "outcome": "success"}
{"log_id": "l004", "agent_id": "agent_A", "action": "delete_record", "context": {"role": "admin", "env": "prod"}, "outcome": "denied"}
{"log_id": "l005", "agent_id": "agent_B", "action": "read_file", "context": {"role": "user", "env": "staging"}, "outcome": "success"}
{"log_id": "l006", "agent_id": "agent_A", "action": "read_file", "context": {"role": "admin", "env": "prod"}, "outcome": "success"}
{"log_id": "l007", "agent_id": "agent_C", "action": "send_email", "context": {"role": "admin", "env": "prod"}, "outcome": "success"}
{"log_id": "l008", "agent_id": "agent_C", "action": "read_file", "context": {"role": "admin", "env": "prod"}, "outcome": "success"}
{"log_id": "l009", "agent_id": "agent_B", "action": "send_email", "context": {"role": "user", "env": "staging"}, "outcome": "success"}
{"log_id": "l010", "agent_id": "agent_D", "action": "read_file", "context": {"role": "viewer", "env": "prod"}, "outcome": "success"}
```

### Step 2: Extract policies via CLI

```bash
aumai-policyminer extract \
  --logs sample_logs.jsonl \
  --min-support 0.1 \
  --min-confidence 0.5 \
  --output my_policies.json \
  --name "Sample Agent Policies"
```

Output:

```
Parsed 10 valid log entries.
Mined N policies.
Saved policy set to my_policies.json
Policy Set: Sample Agent Policies
...
```

### Step 3: Format the results

View as Markdown:

```bash
aumai-policyminer format \
  --policies my_policies.json \
  --output-format markdown
```

### Step 4: Use the Python API

```python
from pathlib import Path
from aumai_policyminer.core import LogParser, PolicyExtractor, PolicyFormatter

# Parse
parser = LogParser()
logs = parser.parse_file(Path("sample_logs.jsonl"))
print(f"Loaded {len(logs)} logs, skipped {parser.skipped_count}")

# Extract
extractor = PolicyExtractor(min_support=0.1, min_confidence=0.5, min_lift=1.0)
policy_set = extractor.extract(logs, name="Sample Agent Policies")

# Display
print(f"\nFound {len(policy_set.policies)} policies:\n")
for policy in policy_set.policies:
    print(f"  {policy.policy_id}: {policy.description}")
```

### Step 5: Inspect individual policies

```python
for policy in policy_set.top_policies(5):
    print(f"Policy: {policy.policy_id}")
    print(f"  When:       {policy.antecedent}")
    print(f"  Then:       {policy.consequent}")
    print(f"  Support:    {policy.support:.1%}")
    print(f"  Confidence: {policy.confidence:.1%}")
    print(f"  Lift:       {policy.lift:.2f}")
    print()
```

---

## Common Patterns and Recipes

### Pattern 1: Generating synthetic logs for testing

```python
import json
import random
from pathlib import Path
from datetime import datetime, timezone

roles = ["admin", "viewer", "analyst", "operator"]
actions = ["read_file", "write_file", "send_email", "delete_record", "approve"]
envs = ["prod", "staging", "dev"]

random.seed(42)
records = []
for i in range(500):
    role = random.choices(roles, weights=[0.2, 0.4, 0.3, 0.1])[0]
    # Admins tend to write and delete more
    if role == "admin":
        action = random.choices(actions, weights=[0.3, 0.3, 0.2, 0.15, 0.05])[0]
    else:
        action = random.choices(actions, weights=[0.5, 0.1, 0.2, 0.05, 0.15])[0]
    records.append({
        "log_id": f"l{i:04d}",
        "agent_id": f"agent_{random.choice('ABCDE')}",
        "action": action,
        "context": {"role": role, "env": random.choice(envs)},
        "outcome": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

Path("synthetic_logs.jsonl").write_text(
    "\n".join(json.dumps(r) for r in records), encoding="utf-8"
)
print("Generated 500 synthetic log entries.")
```

### Pattern 2: Filtering policies by action type

```python
from aumai_policyminer.core import LogParser, PolicyExtractor

parser = LogParser()
logs = parser.parse_file(Path("synthetic_logs.jsonl"))

extractor = PolicyExtractor(min_support=0.05, min_confidence=0.6)
policy_set = extractor.extract(logs)

# Only show policies about deletions (potentially risky)
deletion_policies = [
    p for p in policy_set.policies if p.consequent == "delete_record"
]
print(f"Deletion policies: {len(deletion_policies)}")
for p in deletion_policies:
    print(f"  {p.description}")
```

### Pattern 3: Saving and loading policy sets

```python
from aumai_policyminer.core import PolicyFormatter
from aumai_policyminer.models import PolicySet
from pathlib import Path
import json

formatter = PolicyFormatter()

# Save
formatter.to_json_file(policy_set, Path("policies_v1.json"))

# Load later
data = json.loads(Path("policies_v1.json").read_text(encoding="utf-8"))
loaded = PolicySet.model_validate(data)
print(f"Loaded {len(loaded.policies)} policies from {loaded.generated_at}")
```

### Pattern 4: Using strict thresholds for high-stakes governance

For security-critical applications, use tight thresholds to only surface the
most reliable patterns:

```python
from aumai_policyminer.core import PolicyExtractor

# Strict mode: only very frequent, very reliable, highly specific patterns
extractor = PolicyExtractor(
    min_support=0.10,      # at least 10% of all actions
    min_confidence=0.85,   # reliable 85% of the time
    min_lift=2.0,          # twice as likely as random
)
policy_set = extractor.extract(logs, name="High-Confidence Governance Policies")
print(f"High-confidence policies: {len(policy_set.policies)}")
```

### Pattern 5: CI integration — fail if unexpected policies appear

Use in a CI/CD pipeline to detect unexpected behavioral patterns before
deploying a new agent version:

```python
import sys
from aumai_policyminer.core import LogParser, PolicyExtractor
from pathlib import Path

BANNED_ACTIONS = {"delete_record", "override_safety"}

parser = LogParser()
logs = parser.parse_file(Path("staging_logs.jsonl"))
extractor = PolicyExtractor(min_support=0.02, min_confidence=0.7)
policy_set = extractor.extract(logs)

violations = [
    p for p in policy_set.policies
    if p.consequent in BANNED_ACTIONS and p.confidence > 0.5
]

if violations:
    print("FAIL: unexpected high-confidence policies for banned actions:")
    for v in violations:
        print(f"  {v.description}")
    sys.exit(1)
else:
    print("OK: no banned action policies found.")
```

---

## Troubleshooting FAQ

**Q: `extract` returned zero policies even with a large log file.**

A: Try lowering `--min-support` and `--min-confidence`. With the default
thresholds (`min_support=0.05`, `min_confidence=0.6`), patterns that appear in
less than 5% of logs are discarded. For small log files (< 100 entries), try
`--min-support 0.01`.

**Q: `parse_file` skips many lines. How do I find out what is wrong?**

A: After calling `parse_file`, check `parser.skipped_count`. To diagnose
individual lines, iterate the file manually and try `BehaviorLog.model_validate`
on each line — the Pydantic error will tell you exactly which field is invalid.

**Q: All my policies have `lift=1.0`. What does that mean?**

A: A lift of 1.0 means the context feature provides no additional information
beyond the baseline action frequency — the action is equally likely regardless
of the context. This can happen when your context fields are poorly correlated
with action choices. Try using more discriminative context fields.

**Q: The same action appears in many policies for different context keys.**

A: This is expected — the miner produces one rule per `(context_key,
context_value, action)` triple. If an action like `read_file` is common across
all contexts, it will appear in many rules with low lift. Filter by `lift > 1.5`
to surface only the contextually-specific patterns.

**Q: My context values contain nested objects.**

A: The extractor serializes context values with `str()`. Nested objects will
appear as their Python string representation (e.g., `"{'nested': 'value'}"`).
Flatten your context before logging for cleaner policy antecedents.

**Q: `PolicySet.model_validate` fails on a JSON file.**

A: Ensure your JSON file was produced by `formatter.to_json_file` or
`policy_set.model_dump_json`. Manual edits that violate the Pydantic schema
(e.g., `confidence` outside `[0, 1]`) will cause validation errors.

---

## Next Steps

- Read the [API Reference](api-reference.md) for complete class/method documentation
- Explore [examples/quickstart.py](../examples/quickstart.py) for runnable demos
- Integrate with [aumai-neurosymbolic](https://github.com/AumAI/aumai-neurosymbolic)
  to convert mined policies to symbolic rules
- Join the [Discord community](https://discord.gg/aumai)

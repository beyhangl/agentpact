<p align="center">
  <strong>agentpact</strong>
</p>
<p align="center">Agent Behavioral Contracts — Design-by-Contract for AI agents.<br>Declare what agents must/must not do. Enforce at runtime. Detect drift. Generate compliance docs.</p>

[![License](https://img.shields.io/github/license/beyhangl/agentpact)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue)](https://pypi.org/project/agentpact/)

---

## What is this?

TypeScript added types to JavaScript. **agentpact adds behavioral types to AI agents.**

Guardrails check individual messages. agentpact checks agent **behavior across entire sessions** — enforcing contracts, detecting drift, triggering recovery, and generating compliance documentation.

```python
from agentpact import contract

@contract(
    preconditions=["user.is_authenticated"],
    invariants=["no_pii_in_output", "cost < $0.50"],
    must_call=["verify_identity"],
    must_not_call=["delete_account"],
    max_drift=0.15,
    on_violation="escalate_to_human",
)
async def customer_service_agent(query: str) -> str:
    ...
```

---

## The Problem

**Guardrails check messages. Nobody checks behavior.**

| What exists (guardrails) | What's missing (contracts) |
|---|---|
| "Is this response safe?" | "Has this agent been behaving correctly for the last 20 turns?" |
| Per-message validation | Session-level behavioral monitoring |
| Binary pass/fail | Drift detection with tolerance bounds |
| Block or raise error | Recovery strategies (retry, escalate, fallback) |
| No composition guarantees | Provable: A satisfies C_A, B satisfies C_B → A→B satisfies C_AB |
| No compliance output | Generates EU AI Act Annex IV documentation |

An agent can pass every guardrail check on every individual message and still exhibit dangerous **behavioral drift** — gradually increasing costs, slowly deviating from its task, or subtly changing its tool usage patterns over 50+ turns.

agentpact catches this.

---

## Key Concepts

### Contract = (Preconditions, Invariants, Governance, Recovery)

```
Contract
├── Preconditions    — what must be true BEFORE the agent runs
├── Invariants       — what must remain true THROUGHOUT the session
├── Postconditions   — what must be true AFTER the agent finishes
├── Governance       — policies on tool access, cost, timing
└── Recovery         — what to do when violations occur
```

### Session-Level, Not Message-Level

agentpact tracks state across the **entire agent session**. It can express:

- "The agent must authenticate before accessing user data" (temporal ordering)
- "Cost must not increase by more than 10% per turn on average" (drift bounds)
- "If the agent deviates, it must self-correct within 3 actions" (recovery)

### Probabilistic Compliance

LLMs are non-deterministic. Contracts define `(p, delta, k)-satisfaction`:
- The agent satisfies the contract with probability **p**
- Within drift tolerance **delta**
- Over **k** actions

This maps directly to SLAs and regulatory requirements.

---

## How It's Different

| | NeMo Guardrails | Guardrails AI | Microsoft AGT | **agentpact** |
|---|---|---|---|---|
| Scope | Dialog flow | I/O validation | Security policy | **Behavioral contracts** |
| State | Stateless | Stateless | Per-call | **Session-level** |
| Drift detection | No | No | No | **Yes** |
| Recovery specs | No | No | Circuit breakers | **First-class** |
| Composition | No | No | No | **Formal guarantees** |
| Compliance docs | No | No | No | **EU AI Act Annex IV** |
| Stars | 5,934 | 6,641 | 790 | New |

---

## Features

| Feature | Description |
|---------|-------------|
| **Contract decorator** | `@contract(...)` wraps any agent function with behavioral enforcement |
| **Built-in predicates** | Cost limits, tool rules, output validation, timing constraints, drift bounds |
| **Session tracking** | Stateful monitoring across entire agent runs, not just individual messages |
| **Drift detection** | Detects gradual behavioral changes — cost creep, latency creep, pattern shifts |
| **Recovery strategies** | Log, warn, block, escalate to human, retry with constraints, fallback agent |
| **Formal composition** | Compose contracts across multi-agent pipelines with provable guarantees |
| **Compliance export** | Generate EU AI Act Annex IV documentation from contract specifications |
| **Framework adapters** | OpenAI, Anthropic, Gemini, LangGraph, Pydantic AI, CrewAI |
| **YAML contracts** | Declarative contract files for non-code configuration |
| **CLI tools** | `agentpact init`, `agentpact validate`, `agentpact report` |
| **pytest plugin** | `@pytest.mark.contracted` marker, contract fixtures, violation assertions |
| **evalcraft integration** | Uses evalcraft spans and scorers as contract predicates |

---

## Install

```bash
pip install agentpact

# With framework adapters
pip install "agentpact[openai]"
pip install "agentpact[anthropic]"
pip install "agentpact[langchain]"

# Everything
pip install "agentpact[all]"
```

---

## Quick Start

### 1. Define a contract

```python
from agentpact import contract

@contract(
    must_call=["lookup_order"],
    must_not_call=["delete_account", "modify_payment"],
    cost_limit=0.50,
    max_latency_ms=5000,
    on_violation="block",
)
def support_agent(client, query: str) -> str:
    return run_agent(client, query)
```

### 2. The contract enforces behavior at runtime

```
✓ support_agent called lookup_order
✓ Cost: $0.0003 (limit: $0.50)
✓ Latency: 1,200ms (limit: 5,000ms)
✗ VIOLATION: agent called modify_payment (blocked by must_not_call)
  → Recovery: blocked execution, raised ContractViolation
```

### 3. Detect drift across sessions

```python
from agentpact import DriftMonitor

monitor = DriftMonitor(
    metric="cost_per_turn",
    window=10,
    max_drift_pct=0.15,  # alert if cost grows >15%/turn
)

# Feed session data
for session in daily_sessions:
    monitor.record(session)

report = monitor.check()
if report.has_drift:
    print(f"Cost drift detected: {report.slope_pct:+.1%}/turn")
```

### 4. Generate compliance documentation

```bash
agentpact report --format markdown --standard eu-ai-act
# Generates Annex IV technical documentation from your contract specs
```

---

## YAML Contract Format

```yaml
# contracts/support_agent.yaml
name: support_agent
version: "1.0"
description: Customer support agent for ShopEasy

preconditions:
  - user.is_authenticated
  - user.has_active_session

invariants:
  - no_pii_in_output
  - cost < 0.50
  - latency_per_turn < 3000

governance:
  must_call:
    - lookup_order
  must_not_call:
    - delete_account
    - modify_payment
    - access_admin_panel
  max_turns: 20
  max_total_cost: 1.00

recovery:
  on_violation: escalate_to_human
  max_retries: 2
  fallback: safe_response_agent

compliance:
  standard: eu-ai-act
  risk_tier: limited
  human_oversight: required_on_violation
```

---

## Academic References

This project is grounded in peer-reviewed research on agent behavioral specification and runtime enforcement:

| Paper | Venue | Key Contribution |
|-------|-------|-----------------|
| [Agent Behavioral Contracts (ABC)](https://arxiv.org/abs/2602.22302) | arXiv, Feb 2026 | Formal framework mapping Design-by-Contract to agents. `(p, delta, k)-satisfaction` with drift bounds. AgentAssert prototype detected 5.2-6.8x more violations than uncontracted agents. |
| [AgentSpec](https://arxiv.org/abs/2503.18666) | ICSE 2026 | Lightweight DSL for runtime constraints. 90%+ prevention rate, sub-ms overhead. Auto-generates rules via LLM with 95.56% precision. |
| [Pro2Guard](https://arxiv.org/abs/2508.00500) | arXiv, Aug 2025 | Predictive enforcement using DTMCs. Anticipates violations before they happen using learned execution traces. |
| [Agent-C](https://arxiv.org/abs/2512.23738) | arXiv, Dec 2025 | Temporal safety constraints via SMT solving. 100% conformance on customer service and airline benchmarks. |
| [Runtime Governance: Policies on Paths](https://arxiv.org/abs/2603.16586) | arXiv, Mar 2026 | Execution path as governance object. Shows prompt-level instructions and static ACLs are special cases of path policies. |
| [Agent Contracts (Resource-Bounded)](https://arxiv.org/abs/2601.08815) | COINE/AAMAS 2026 | Unifies resource, temporal, and quality governance with conservation laws for multi-agent delegation. |
| [DbC Neurosymbolic Layer](https://arxiv.org/abs/2508.03665) | arXiv, Aug 2025 | Contract layer mediating every LLM call with semantic requirements and probabilistic remediation. |

---

## Relationship to Evalcraft

agentpact is the **runtime enforcement** companion to [evalcraft](https://github.com/beyhangl/evalcraft) (the testing companion):

| | evalcraft | agentpact |
|---|---|---|
| When | Post-hoc (after the run) | Real-time (during the run) |
| What | "Did the agent behave correctly?" | "Is the agent behaving correctly right now?" |
| How | Cassette replay + assertions | Contract enforcement + drift detection |
| Analogy | pytest | mypy / TypeScript |

They share infrastructure: agentpact can use evalcraft's span capture, scorers, and framework adapters as building blocks.

---

## Contributing

```bash
git clone https://github.com/beyhangl/agentpact
cd agentpact
pip install -e ".[dev]"
pytest
```

PRs welcome. Please open an issue first for significant changes.

---

## License

MIT © 2026 Beyhan Gul. See [LICENSE](LICENSE).

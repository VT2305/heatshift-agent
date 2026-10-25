# HeatShift Supervisor architecture

```mermaid
flowchart TB
  E[Heat / worker / task / zone event] --> P[PERCEIVE]
  P --> S[get_site_state]
  P --> H[get_heat_state]
  S --> A[ASSESS]
  H --> R[get_safety_constraints]
  R --> A
  A -->|Compliant| M[MONITOR]
  A -->|Conflict| O[PLAN: OR-Tools scheduler]
  O --> V[VERIFY: deterministic validator]
  V -->|Fail; max 2 attempts| O
  V -->|Pass| I[Impact calculator]
  I --> X[Plain-English explanation]
  X --> C[Decision Certificate]
  C --> Q{Supervisor approval}
  Q -->|Approve| PUB[Publish new plan]
  Q -->|Reject/Edit| M
  PUB --> AU[Audit log]
  M --> E
  AU --> E
```

## Three layers of truth

1. **Regulatory truth** — versioned deterministic rules; LLM authority = zero.
2. **Operational truth** — worker/task/site/WBGT state; LLM may read and orchestrate.
3. **Decision language** — explanations, tool selection and dialogue.

## Critic-proof statement

> Rules determine what is allowed. The optimiser finds feasible plans. The supervisor agent decides when to invoke them, coordinates tools, validates results, explains trade-offs, and stops at a human approval boundary.

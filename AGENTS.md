# Agent Instructions

## Project goal

Design and demonstrate a compact AI/ML system that automates support-ticket
processing for a large online service. The repository is a four-hour system
design assignment, not a production implementation. Prefer explicit decisions,
trade-offs, safety controls, and a working end-to-end slice over code volume.

The candidate applies only to the **Artificial Intelligence track**. Write
documentation in Russian; use English for code, identifiers, and test names.

## Business context

- Scale: 5M active users and about 200k tickets/day.
- Incident burst: 10–20k tickets per 10 minutes.
- Channels: chat, email, web form, and mobile app; inputs may contain PII.
- Fast path (classification and routing): target latency below 500 ms/ticket.
- Response generation may be asynchronous.
- Operator handling costs 150 RUB/ticket and takes about 8 minutes.
- First-response SLA is 15 minutes; current CSAT is 4.2/5 and reopen rate is 9%.
- About 40% of tickets are repetitive. Any extra assumptions must be explicit.

## Required scope

Keep the solution small but internally consistent. Required deliverables:

- `README.md`: two-minute overview, local run instructions, demonstrated paths,
  implementation/design boundary, assumptions, limitations, and business value.
- `docs/architecture.md`: target components, data flow, sync/async boundaries,
  storage, integrations, human review, fallback paths, and Mermaid diagrams.
- `docs/ml.md`: rules vs classic ML vs retrieval/embeddings vs LLM, baselines,
  data and labeling, evaluation, confidence thresholds, and abstention.
- `docs/monitoring.md`: technical, ML, product, and LLM-cost metrics; initial
  alerts; model degradation vs input drift; evidence of business value.
- `docs/risks-and-ops.md`: 3–4 key points each for highload/reliability and for
  privacy/safety/risk.
- `AI_USAGE.md`: honest, incremental record of AI contributions, rejected
  suggestions, candidate decisions, verification, failures, and corrections.
- `SELF_REVIEW.md`: weakest area, assumptions, unresolved risks, next two days,
  production gaps, non-automatable areas, and pilot stop criteria.
- Minimal Python PoC plus a smoke test or demo script.

`docs/product.md` is optional for this track. If included, keep it brief and
decision-oriented: stakeholder pain/value, online metrics, and hypotheses.
Detailed ROI, rollout, and pilot calculations are out of scope unless needed
to justify an architecture decision. Do not create `WORKLOG.md`.

## PoC acceptance criteria

Demonstrate exactly enough for two end-to-end paths:

1. Happy path: accept a mock ticket, classify topic and risk, retrieve a
   relevant knowledge item or similar case, produce a draft/route, and persist
   an auditable decision record.
2. Risky/fallback path: risky or low-confidence input must be routed to a human;
   it must never be auto-closed. Show graceful behavior when generation is
   unavailable.

Mocks, rules, small local data, and deterministic substitutes are acceptable.
Document every simplification and its target-architecture replacement.

## Design constraints

- Keep classification/routing independent from slow LLM generation.
- Never send raw PII to an external LLM; redact first or keep processing local.
- Require human review for payments, account security, legal/safety issues, and
  other high-risk categories.
- Treat retrieved and user-provided text as untrusted; mitigate prompt injection.
- Store model/rule versions, confidence, evidence, action, and fallback reason.
- Bound LLM cost with routing, token limits, caching/deduplication, and budgets.
- On uncertainty or dependency failure, abstain and preserve operator workflow.

## Working principles

- Keep documentation, PoC behavior, tests, diagrams, and README consistent.
- Use deterministic, testable behavior where a real model is unnecessary.
- Do not invent evaluation results; label estimates and assumptions clearly.
- Avoid Kubernetes, model training, full MLOps, feature stores, and detailed UI.
- After each logical work block, update `AI_USAGE.md` in Russian.

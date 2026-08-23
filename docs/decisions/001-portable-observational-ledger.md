# ADR-001: Use a portable agent-authored ledger inspired by Observational Memory

## Status

Accepted

## Date

2026-08-22

## Context

Coding-agent sessions are isolated by harness, model context window, and account/session limits. A developer needs to move between Claude Code, Codex, Grok, Pi, and other CLIs while retaining project decisions, failed approaches, verification, and continuation state.

Mastra Observational Memory demonstrates the value of separating episodic observations from consolidated reflections and injecting a bounded stable memory projection. Its runtime uses automatic Observer and Reflector model calls. The pi-observational-memory implementation adds a source-backed session ledger, branch-local projection, tombstones, and automatic turn-end processing.

Those automatic designs assume control over one agent runtime. This project must work across unrelated harnesses whose hooks, transcripts, stop semantics, trust models, and skill invocation syntax differ.

## Decision

Use a host-neutral, append-only JSONL project ledger with three semantic record types:

- observations for coherent durable work;
- handoffs for the continuation frontier;
- reflections for scope-aware durable consolidation.

Agents author semantic records through one portable Agent Skill. Deterministic host adapters may inject bounded context, track lifecycle state, or request a missing checkpoint, but they do not summarize transcripts or write semantic records automatically.

Use Observational Memory as the conceptual model, not as a requirement to reproduce Mastra's automatic background agents. Preserve original records; reflections change retrieval projection rather than deleting or rewriting history.

## Alternatives Considered

### Automatic Observer and Reflector model calls

- Pros: low-friction capture and closer parity with Mastra.
- Cons: requires transcript access, model/provider configuration, token accounting, privacy policy, background execution, and consistent hooks that do not exist across all supported harnesses.
- Rejected for the portable core. A host-specific optional extension may be considered later without changing the ledger protocol.

### Vector database or graph memory

- Pros: semantic retrieval and richer relationships.
- Cons: introduces services, dependencies, opaque ranking, migration, and synchronization requirements for a problem that is small enough for deterministic structured filtering.
- Rejected. File-based inspectability and portability are primary requirements.

### One universal `/project-context` command

- Pros: identical user experience.
- Cons: hosts expose incompatible invocation surfaces. Codex uses `$project-context`, Pi uses `/skill:project-context`, and some hosts have no documented skill slash command.
- Rejected as a product guarantee. The installer records exact native syntax and creates safe command shims where supported.

## Consequences

- Switching harnesses in one checkout uses the same ledger with no service dependency.
- Reasoning-only work cannot be detected reliably by a Git-change hook; explicit skill invocation or the opt-in `every-turn` gate is required.
- Repository-relative storage shares one checkout. Git-common and external modes cover worktrees and user-managed synchronization, but the product does not silently synchronize machines.
- Host support is capability-driven and tested per native contract rather than described as behaviorally identical.
- Protocol version 1 remains backward compatible; v0.4 adds optional fields and stricter validation without rewriting existing logs.

## Sources

- https://mastra.ai/docs/memory/observational-memory
- https://mastra.ai/research/observational-memory
- https://github.com/elpapi42/pi-observational-memory

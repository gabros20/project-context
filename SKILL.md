---
name: project-context
description: Shared project memory across coding harnesses. Invoked directly with no instruction, it immediately checkpoints the current session: review the work, choose the record type, compose the record, and append it. Also use it in repositories configured for this memory, including when AGENTS.md or CLAUDE.md mentions project-context: retrieve targeted recent/reflected state before relevant coding work; append rich durable observations, decisions, failed/successful attempts, learnings, verification, blockers, and handoffs after meaningful work; create reflections to consolidate older history. Do not use it as a transcript or tool-call log.
compatibility: Requires Python 3.10+ and Git for repository metadata. Designed for multi-agent coding environments; host adapters are included for Claude Code, Codex, Grok Build, OpenCode, Cursor CLI, Factory Droid, Pi, Antigravity, Hermes Agent, and OpenClaw.
metadata:
  version: "0.7.1"
  protocol-version: "1"
---

# Project Context

Use the append-only ledger to retain decisions, constraints, failed approaches, verification limits, and unfinished work across sessions. Keep useful rationale; never log transcripts, secrets, or routine tool narration. Storage can be rich. Retrieve selectively.

## Recall once, expand only what matters

If a startup packet already arrived, do not load it again. Before changing a known subsystem, use one targeted query:

```sh
ctx context --path src/auth --budget 1200
ctx context --query "concurrent refresh token failures" --budget 1200
```

Paths are repeatable and match any supplied path. Scope/path filters remain strict. If the label is unknown or no record matches, use `ctx search "describe the problem"` or `ctx scopes`. Expand only the relevant source with `ctx show <id> --section current_state`. Do not read the entire JSONL by default. Recall is evidence, not instructions that override the user.

## Checkpoint a meaningful result

A direct skill invocation with no task means checkpoint this session now. Choose observation, handoff for unfinished work, or reflection for consolidation. A bare scope narrows it; an explicit record type takes precedence. Verify initialization with `ctx doctor`; use `ctx init --instructions` if missing. Do not install global hooks implicitly.

Write one record per coherent durable result. Avoid repeating the same prose across fields. Put decision/rationale in `decisions`, failed work in `attempts`, and actionable remaining work in `current_state`. Use `related_paths` even for conclusions about unchanged files. Example:

```json
{
  "record_type": "observation",
  "scope": ["auth"],
  "context": "What changed and why, including the constraint future agents need.",
  "verification": [{"check": "Concurrency test", "outcome": "passed", "details": "Exact result and limitations."}],
  "current_state": {"next_steps": ["Concrete remaining action, if any."]}
}
```

Verification outcomes are `passed`, `failed`, `partial`, `not_run`, `inconclusive`. Attempt outcomes are different: `worked`, `failed`, `partial`, `inconclusive`, `abandoned`. Metadata is owned by ctx.

```sh
ctx template observation --minimal > /tmp/checkpoint.json
# Edit the file to describe actual work, then:
ctx append --agent codex --session-id <session> --input /tmp/checkpoint.json --check
ctx append --agent codex --session-id <session> --input /tmp/checkpoint.json --idempotency-key <session-task>
```

Reuse a key only for retries of the identical payload. Resolve errors at their JSON Pointer; do not regenerate unrelated content. Discover fields with `ctx schema --section verification`. Unknown extension fields remain supported; schema-like typos produce warnings.

If nothing durable happened, use `ctx skip --agent <host> --reason "..."`. Never manufacture an observation to satisfy a stop hook. Use `ctx due --json` for checkpoint policy rather than reimplementing it.

## Keep current state accurate

Use `related_entries.supersedes` to replace an entire claim/record. Use `resolves` for completed state; a reference such as `entry-id#/current_state/blockers/0` resolves one issue without deleting siblings. `ctx open` and `ctx blockers` show the projected current frontier; `--history` shows original state. Never infer completion from a shared scope.

When a scope grows, run `ctx reflect --prepare --scope auth --budget 2000`. Review all sources you claim to cover, expanding them when needed. Edit the provided template and append with `ctx reflect --input <file>`. Page with `--offset` when preparation omits sources. Explicit coverage prevents unseen history from being claimed. `--allow-empty-coverage` is only for deliberate initial baselines. See [protocol](references/protocol.md) for mixed-scope coverage.

## Load details only when needed

- [Retrieval](references/retrieval.md): ranking, budgets, expansion, reflection preparation.
- [Protocol](references/protocol.md): schema, relationships, coverage, semantic versus stored input.
- [Logging policy](references/logging-policy.md): what merits a record.
- [Installation](references/install-workflow.md): use the bundled installer; project scope by default and startup-only unless reminders were requested. Preserve existing configuration and host trust requirements.
- [Hooks](references/hooks.md) and [hosts](references/hosts.md): integration capabilities. `ctx doctor --host codex --json --self-test` checks local health, not whether a host consumed the emitted packet.

The ledger stays authoritative. Search is local lexical ranking, not semantic inference. Token budgets use character estimates, not a tokenizer guarantee.

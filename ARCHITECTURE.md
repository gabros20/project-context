# Project Context v0.5 — Architecture

## 1. Objective

`project-context` is a host-neutral shared episodic-memory protocol for coding agents. Independent sessions in different agent harnesses coordinate through one append-only `.agent/PROJECT_CONTEXT.jsonl` rather than attempting to share hidden model state.

A fresh agent should be able to recover: what happened; why decisions were made; approaches that worked or failed; verified facts versus hypotheses; changed code/artifacts; current blockers/open questions; and the exact frontier of unfinished work.

The system supports Claude Code, Codex, Grok Build, OpenCode, Cursor CLI, Factory Droid, Pi/pi-mono, Google Antigravity CLI, Hermes Agent, and OpenClaw through thin adapters.

The observation/reflection projection is inspired by Mastra Observational Memory and the pi-observational-memory implementation. Unlike those runtime-specific systems, the portable core does not require automatic background model calls or transcript ownership. See [ADR-001](docs/decisions/001-portable-observational-ledger.md).

## 2. Architectural rule

```text
                HOST-NEUTRAL CORE

 AGENTS.md ──────── project bootstrap/policy
       │
       ▼
 SKILL.md ───────── semantic protocol and agent behavior
       │
       ▼
 scripts/ctx.py ─── deterministic read/write/query/lifecycle runtime
       │
       ▼
 .agent/PROJECT_CONTEXT.jsonl
        append-only durable project memory

                HOST-SPECIFIC EDGE

 Claude/Codex/Grok/Cursor/Droid/Antigravity → native JSON hooks
 OpenCode                               → generated JS plugin
 Pi                                     → generated TS extension
 Hermes                                 → generated Python plugin
 OpenClaw                               → generated internal hook pack
```

**Adapters never own the memory model.** They only translate host events into normalized `ctx` operations.

## 3. Information model

### Observation

Rich episodic memory for one coherent unit of durable work. Its narrative `context` may be substantial. Structured sections make it filterable:

- `decisions`: decision, rationale, rejected/accepted alternatives;
- `attempts`: approach, outcome, reason, evidence, learning;
- `learnings`: typed fact/invariant/constraint/convention/gotcha/hypothesis/open question plus confidence;
- `changes`: commits, files, artifacts and purpose;
- `verification`: checks and exact outcomes;
- `current_state`: working, remaining, blockers, open questions, next steps;
- `related_entries`: supersedes/resolves/related provenance links.

### Reflection

A new append-only record that consolidates durable understanding from older observations. It never rewrites or deletes history. Coverage is scope-aware, calculated under the append lock, and points to the source range and supporting entry IDs. A reflection never advances an unrelated subsystem's frontier.

### Handoff

A frontier record optimized for another agent taking over incomplete/non-obvious work.

## 4. Storage vs retrieval

Raw storage is rich JSONL with full field names such as `version`, `timestamp`, `record_type`, and `importance`. Token efficiency is obtained at retrieval time, not by cryptic schema keys.

Default startup strategy:

```text
latest relevant reflection
          +
important unreflected tail
          +
targeted scope/path matches
          ↓
bounded compact plaintext projection
```

Agents should normally use `ctx startup`, `ctx context --scope`, or `ctx context --path`, not load the entire log.

## 5. Normalized lifecycle

The portable runtime recognizes:

```text
session-start
turn-start
pre-invocation
compact-before
compact-after
stop
session-end
```

Semantics:

- `session-start`: record session/Git baseline; inject bounded startup context where the host has an injection channel.
- `turn-start`: record per-turn Git fingerprint.
- `pre-invocation`: Antigravity-specific bridge combining first invocation injection and turn start.
- `compact-before` / `compact-after`: mark memory-risk boundaries; host adapters may refresh context.
- `stop`: optional missing-checkpoint guard controlled by `checkpoint.stop_gate`.
- `session-end`: close transient session state.

No adapter automatically writes an observation from a transcript. Semantic memory remains agent-authored.

## 6. Host compatibility matrix

| Host | Skill | Instructions | Lifecycle edge | Context injection | Active Stop continuation |
|---|---|---|---|---|---|
| Claude Code | native Agent Skill | `CLAUDE.md` + `AGENTS.md` bridge | native command hooks | SessionStart | yes |
| Codex | `.agents/skills` | `AGENTS.md` | native command hooks | SessionStart/UserPrompt context | yes |
| Grok Build | `.grok/skills`, Agent Skills compatibility | `AGENTS.md`, Claude-compatible instructions | native command hooks | project bootstrap is guaranteed; hook injection kept conservative | audit only |
| OpenCode | native skills + `.agents/skills` compatibility | `AGENTS.md` | JS plugin events | compaction hook; bootstrap via AGENTS | audit only |
| Cursor CLI | native Agent Skills | `AGENTS.md` / `CLAUDE.md` | native hooks JSON | `sessionStart.additional_context` | yes |
| Factory Droid | native skills | `AGENTS.md` | native hooks JSON | `SessionStart.additionalContext` | yes |
| Pi | native skills | `AGENTS.md` / `CLAUDE.md` | TS extension | `before_agent_start` custom message | audit only |
| Antigravity | Agent Skills | `AGENTS.md` / `GEMINI.md` | hooks JSON | `PreInvocation.injectSteps.ephemeralMessage` | yes |
| Hermes | agentskills.io-compatible | `AGENTS.md` | Python plugin | `pre_llm_call` context | `pre_verify` when applicable |
| OpenClaw | Agent Skills | workspace `AGENTS.md` | internal hook pack | `agent:bootstrap` bootstrap file | boundary/audit only |

Not every host exposes equivalent lifecycle semantics. The core intentionally supports **capability degradation**: project instructions + explicit skill commands remain sufficient even if a host has no reliable Stop gate.

Machine-readable details live in `adapters/HOSTS.json`.

## 7. Skills and project instructions

`AGENTS.md` is the canonical repository bootstrap because it is broadly supported. It contains only the invariant contract and tells agents to use `project-context`; detailed protocol lives in `SKILL.md`/references.

For Claude, `ctx init --instructions` preserves an existing `CLAUDE.md` and adds `@AGENTS.md` only when needed. Existing instruction files are appended to, never replaced, and receive a stable `.project-context.bak` before the first modification.

Global skill installation maintains one canonical package under `~/.agent-skills/project-context` and links/copies it into host discovery locations. Generic `~/.agents/skills/project-context` is also installed for compatible harnesses.

## 8. Lifecycle installation model

The skill is self-installing in the sense that an agent can be told:

> Add the project-context lifecycle hooks to this project.

`SKILL.md` instructs it to call the bundled installer. Scope rules are deterministic:

```text
"this project" / "this repo" / "here" → project
"globally" / "all projects" / "for my user" → user
ambiguous → project
```

The agent then reports host detection, created/modified paths, backups, trust/activation steps, and project-context initialization status.

## 9. Safe configuration mutation

Installer invariants:

1. Parse existing JSON before changing it.
2. Refuse invalid/non-object JSON.
3. Preserve unrelated fields and hook groups.
4. Before first modification, write exact original to `*.project-context.bak`.
5. Write changes atomically.
6. Be idempotent on repeated installation.
7. Project scope must never write user/global configuration.
8. Generated plugin/extension/hook files receive the same backup rule.
9. Never bypass host trust/workspace/plugin security decisions.

## 10. Checkpoint modes

`checkpoint.stop_gate` defaults to `off`. `changed-work` requests a checkpoint when the Git fingerprint changed; `every-turn` also covers reasoning-only work. The agent may append a real observation/handoff/reflection or explicitly run `ctx skip` for genuinely non-durable work. Legacy `hooks.stop_check: true` maps to `changed-work`.

This avoids a noisy “log every turn” bureaucracy while still allowing strict teams to enable enforcement.

Lifecycle installation has two explicit profiles. `startup-only` installs the minimum events required to load context at session start and recover it after compaction where the host supports that channel. `full` also installs prompt baselines, Stop checks, and session-boundary tracking. `full` remains the compatibility default; users who only want automatic recovery should select `startup-only`.

Profile changes use managed-entry reconciliation. The installer identifies its own `ctx.py hook ... --host ...` commands, removes only those entries, and then installs the selected profile. Unrelated host configuration survives both directions of a profile switch.

At runtime, `turn-start` reads the repository checkpoint configuration before calculating a fingerprint. When `checkpoint.stop_gate` is `off`, it returns the host's neutral response without running `git status` or writing turn state. This keeps existing full-profile installations cheap while `startup-only` removes the prompt hook entirely on hosts with a native startup event. Antigravity retains `PreInvocation` because it has no separate startup injection event.

## 11. Concurrency and Git

The JSONL is append-only and writes are lock-protected. Records contain Git branch/worktree/HEAD metadata but Git is evidence, not synchronization.

Storage modes make the sharing boundary explicit:

- `repo`: one checkout-local ledger;
- `git-common`: one ledger shared by worktrees in the same clone;
- `external`: an explicit absolute path managed by the user.

Tracking is independently `unmanaged`, `ignored`, or `versioned`. Separate clones and machines still require Git or user-managed synchronization; no hidden transport is implied.

The protocol is independent of which transport is chosen.

## 12. Package layout

```text
project-context-v0.5.0/
├── SKILL.md
├── README.md
├── INSTALL.md
├── ARCHITECTURE.md
├── adapters/
│   ├── HOSTS.json
│   ├── README.md
│   └── templates/          # generated host adapter sources
├── scripts/
│   ├── ctx.py
│   └── install.py
├── assets/
│   ├── PROJECT_CONTEXT.schema.json
│   ├── project-context.example.json
│   ├── AGENTS.snippet.md
│   └── CLAUDE.snippet.md
├── references/
│   ├── protocol.md
│   ├── retrieval.md
│   ├── logging-policy.md
│   └── hooks.md
├── examples/
├── docs/decisions/
├── CHANGELOG.md
└── tests/
```

## 13. Operational flow

```text
SESSION START
    ↓
host adapter / AGENTS bootstrap
    ↓
ctx startup
    ↓
reflection + tail + targeted memory
    ↓
agent works
    ↓
ctx append / handoff / reflect after durable work
    ↓
(optional) Stop guard verifies checkpoint fingerprint
    ↓
SESSION END
```

The durable invariant is simple: **observations preserve episodes, reflections preserve durable understanding, handoffs preserve the work frontier, and host adapters remain disposable plumbing around the same memory core.**

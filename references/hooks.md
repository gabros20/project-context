# Universal lifecycle integration

Lifecycle adapters are optional deterministic plumbing. They normalize each host's native events into the same `ctx hook` API. They never generate semantic observations automatically.

## Normalized lifecycle API

```text
session-start   → establish session baseline; inject startup memory when host supports it
turn-start      → capture a Git fingerprint for the current agent turn
pre-invocation  → Antigravity adapter: first-call context injection + turn baseline
compact-before  → mark compaction boundary
compact-after   → refresh/resume boundary
stop            → optional missing-checkpoint audit/gate
session-end     → close transient session state
```

`checkpoint.stop_gate` controls missing-checkpoint behavior:

- `off` (default): no Stop gate; explicit skill invocation drives checkpointing;
- `changed-work`: request a checkpoint when Git state changed after the turn baseline;
- `every-turn`: request an append or explicit skip after every completed turn, including reasoning-only work.

Legacy `hooks.stop_check: true` is read as `changed-work`. All adapters delegate the decision to `ctx due`/the normalized Stop handler.

## Host adapter matrix

| Host | Explicit invocation | Lifecycle integration | Startup injection | Stop behavior |
|---|---|---|---|---|
| Claude Code | `/project-context` | command hooks | `SessionStart` | block |
| Codex | `$project-context` or `/skills` | command hooks | `SessionStart` | block |
| Grok Build | `/project-context` | compatibility hooks | compatibility-dependent | observe |
| OpenCode | `/project-context` installer shim | generated JS plugin | AGENTS instructions; compaction injection | observe |
| Cursor | `/project-context` | native hooks JSON | `sessionStart` | follow-up message |
| Factory Droid | `/project-context` | native hooks JSON | `SessionStart` | block |
| Pi / pi-mono | `/skill:project-context` | TypeScript extension | first `before_agent_start` | observe at `agent_settled` |
| Antigravity | ask to use the skill | native hooks JSON | first `PreInvocation` | continue |
| Hermes Agent | `/project-context` | Python plugin | first `pre_llm_call` | `pre_verify` when applicable |
| OpenClaw | `/project-context` | internal hook pack | bootstrap file | unavailable |

The table describes the adapter strategy, not a claim that all hosts expose identical lifecycle semantics. `ctx doctor` and `install.py status` should be used to inspect the actual installation.

## Configuration locations

Project-scoped adapters:

```text
Claude Code  .claude/settings.json
Codex        .codex/hooks.json
Grok Build   .grok/hooks/project-context.json
OpenCode     .opencode/plugins/project-context.js
Cursor CLI   .cursor/hooks.json
Droid        .factory/hooks.json
Pi           .pi/extensions/project-context.ts
Antigravity  .agents/hooks.json
Hermes       .hermes/plugins/project-context/
OpenClaw     hooks/project-context/
```

User/global adapters:

```text
Claude Code  ~/.claude/settings.json
Codex        ~/.codex/hooks.json
Grok Build   ~/.grok/hooks/project-context.json
OpenCode     ~/.config/opencode/plugins/project-context.js
Cursor CLI   ~/.cursor/hooks.json
Droid        ~/.factory/hooks.json
Pi           ~/.pi/agent/extensions/project-context.ts
Antigravity  ~/.gemini/config/hooks.json
Hermes       ~/.hermes/plugins/project-context/
OpenClaw     ~/.openclaw/hooks/project-context/
```

## Safety and trust

Installer invariants:

- parse existing JSON before modification;
- refuse malformed/non-object JSON;
- preserve unrelated settings and hook groups;
- create a stable first-original `*.project-context.bak` before changing an existing file;
- write atomically;
- make repeated installation idempotent;
- project scope never writes user/global hook configuration.

Generated JS/TS/Python adapters are also backed up before replacement.

Several hosts require project/workspace trust or explicit hook/plugin enablement. The installer prints the relevant follow-up rather than bypassing host security controls.

## Why not PostToolUse semantic logging?

Tool-call granularity is much too fine. A single meaningful work unit may include dozens of reads, edits, tests, and commands. Hooks may collect transient metadata, but durable observations remain agent-authored after a coherent unit of work.

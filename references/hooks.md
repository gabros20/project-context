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

`hooks.stop_check` is false by default. When enabled, a blocking host is asked to continue only when repository state changed after the turn baseline and no observation/handoff/reflection or explicit `ctx skip` covers the current fingerprint.

## Host adapter matrix

| Host | Skill discovery used by installer | Project instructions | Lifecycle integration | Startup injection | Stop gate |
|---|---|---|---|---|---|
| Claude Code | `.claude/skills` / user `.claude/skills` | `CLAUDE.md` imports `AGENTS.md` | command hooks in settings JSON | yes | yes |
| Codex | `.agents/skills` | `AGENTS.md` | command hooks in `.codex/hooks.json` | yes | yes |
| Grok Build | `.grok/skills` plus `.agents/skills` compatibility | `AGENTS.md` | command hooks under `.grok/hooks/` | host-dependent; AGENTS fallback always exists | audit only in core |
| OpenCode | `.opencode/skills`, also `.agents/skills` | `AGENTS.md` | generated JS plugin | compaction injection + AGENTS fallback | audit only |
| Cursor CLI | `.cursor/skills` | `AGENTS.md` / `CLAUDE.md` | `.cursor/hooks.json` | yes | yes (`followup_message`) |
| Factory Droid | `.factory/skills`, compatible Agent Skills paths | `AGENTS.md` | `.factory/hooks.json` | yes | yes |
| Pi / pi-mono | `.pi/skills` plus compatible Agent Skills paths | `AGENTS.md` / `CLAUDE.md` | generated TypeScript extension | yes, via `before_agent_start` | audit only |
| Antigravity | `.agents/skills`, global Gemini skills dir | `AGENTS.md` / `GEMINI.md` | `.agents/hooks.json` / user hooks | yes, via `PreInvocation.injectSteps` | yes |
| Hermes Agent | user `~/.hermes/skills` | `AGENTS.md` | generated Hermes plugin | yes, via `pre_llm_call` | yes, via `pre_verify` when applicable |
| OpenClaw | `.agents/skills` / workspace skills | workspace `AGENTS.md` | generated internal hook pack | yes, via `agent:bootstrap` bootstrap file | audit/boundary only |

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

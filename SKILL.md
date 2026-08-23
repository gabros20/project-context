---
name: project-context
description: Shared PROJECT_CONTEXT.jsonl project memory. Invoked directly with no instruction, it immediately checkpoints the current session: review the work, choose the record type, compose the record, and append it. Also use it in repositories configured for this memory, including when AGENTS.md or CLAUDE.md mentions project-context: retrieve targeted recent/reflected state before relevant coding work; append rich durable observations, decisions, failed/successful attempts, learnings, verification, blockers, and handoffs after meaningful work; create reflections to consolidate older history. Do not use it as a transcript or tool-call log.
compatibility: Requires Python 3.10+ and Git for repository metadata. Designed for multi-agent coding environments; host adapters are included for Claude Code, Codex, Grok Build, OpenCode, Cursor CLI, Factory Droid, Pi, Antigravity, Hermes Agent, and OpenClaw.
metadata:
  version: "0.5.0"
  protocol-version: "1"
---

# Project Context

Maintain durable shared project memory between independent coding-agent sessions.

## Core invariant

`.agent/PROJECT_CONTEXT.jsonl` is an append-only project memory event stream, not a transcript.

Store enough context that a capable agent unfamiliar with the previous session can understand the relevant project state, why decisions were made, what was tried, what failed or worked, what was learned, what was verified, and what remains open.

Do not optimize records into cryptic fragments. Storage may be rich. Token efficiency comes from targeted retrieval and reflection.

## Direct invocation means "checkpoint this session"

When this skill is invoked directly and the user gives no other instruction, that request is complete
in itself: log the session. Do it now, in full, without asking what happened or which record type to
use. The user is not required to describe the work, name a scope, or write JSON.

1. Confirm the repository is initialized with `ctx doctor`. If it is not, run `ctx init --instructions`
   and say so rather than appending.
2. Choose the record type yourself from what actually happened this session:
   - **observation** — default; a coherent unit of work reached a durable outcome;
   - **handoff** — work is unfinished or non-obvious and another session must continue it;
   - **reflection** — the user asked to consolidate, or `ctx stats` shows a large unreflected tail.
3. Reconstruct the session from the actual conversation and work, following the field guidance in
   **After meaningful work** below.
4. Append it with the matching command, then report the record type, scope, and returned entry id in
   one line.

If the invocation carries an instruction, follow that instruction instead. A bare word narrows scope
(treat it as `scope`); an explicit record type forces that type.

If the session produced no durable project knowledge, do not manufacture a record — run `ctx skip`
as described in **Optional stop-hook response** and say that you skipped and why.

## Before relevant work

If `.agent/project-context.json` or `.agent/PROJECT_CONTEXT.jsonl` exists, use this protocol.

1. Session-start hooks may already have injected a bounded startup packet. Do not redundantly read the full JSONL.
2. Before modifying a known subsystem or path, run a targeted retrieval:

   ```bash
   ctx context --scope <scope>
   ctx context --path <repo-relative-path>
   ```

3. Expand history only if the targeted packet is insufficient.

Read `references/retrieval.md` when choosing a more specialized query.

## After meaningful work

Create one rich `observation` after a coherent unit of durable work. Do not create one record per tool call.

The observation should preserve, when applicable:

- background and outcome in `context`;
- decisions and rationale;
- alternatives considered or rejected;
- attempts that worked, failed, were partial, inconclusive, or abandoned;
- learnings with epistemic type and confidence;
- changed commits/files/artifacts;
- explicit `related_paths` when the durable result affects paths that are not currently dirty;
- verification and exact outcomes;
- current working state, blockers, open questions, and next steps;
- superseded/resolved/related context entries.

Prefer structured semantic JSON piped to the CLI:

```bash
cat <<'JSON' | ctx append --agent <host-name> --input -
{
  "record_type": "observation",
  "importance": "high",
  "scope": ["auth"],
  "context": "Rich durable context...",
  "attempts": [
    {
      "approach": "...",
      "outcome": "failed",
      "reason": "...",
      "learning": "..."
    }
  ],
  "current_state": {
    "status": "in_progress",
    "next_steps": ["..."]
  }
}
JSON
```

The CLI adds `version`, `timestamp`, `entry_id`, repository/Git metadata, and session metadata. Do not manually fabricate fields the CLI derives.

Read `references/logging-policy.md` when uncertain whether something deserves durable memory.

## Handoff

Use a handoff when another session/agent must continue unfinished or non-obvious work:

```bash
cat event.json | ctx handoff --agent <host-name> --input -
```

A handoff must contain useful `current_state` including remaining work, blockers/open questions where applicable, and concrete next steps.

## Reflection

Use reflection to consolidate a growing history without deleting observations.

Create a reflection when a subsystem has accumulated enough observations that a new agent would benefit from one durable state summary, or when `ctx stats` reports a substantial tail since the last reflection.

```bash
cat reflection.json | ctx reflect --agent <host-name> --input -
```

The reflection should preserve durable architecture, decisions, constraints, known failed approaches, successful approaches, completed work, and open work. The CLI can fill missing coverage boundaries from the log.

Automatic coverage is scope-aware and requires at least one unreflected observation or handoff in that scope. Use `--allow-empty-coverage` only when deliberately recording an initial durable baseline.

See `references/protocol.md` for reflection coverage semantics.

## Retrieval commands

Common operations:

```bash
ctx startup
ctx latest 8
ctx context --scope auth
ctx context --path src/auth/session.ts
ctx since 2026-08-17T09:30:00Z
ctx decisions --scope auth
ctx attempts --scope auth --outcome failed
ctx open --scope auth
ctx blockers
ctx due --json
ctx validate
ctx stats
ctx doctor
```

Raw JSONL is available with `--format jsonl`; normal agent use should prefer projected plain text.


## Installing lifecycle integration from the skill

When the user asks to add, install, configure, or check project-context lifecycle integration, use the bundled `scripts/install.py`; do not hand-edit host configuration unless the installer reports an unsupported case.

Interpret scope as follows:

- “this project”, “this repo”, or “here” → project scope;
- “globally”, “all projects”, or “for my user” → user scope;
- ambiguous wording → project scope. Never silently choose global scope.

Examples:

```bash
# Detect installed/supported hosts
python3 scripts/install.py detect

# Install skill + project lifecycle integration for detected hosts
python3 scripts/install.py skills --hosts auto --scope project --project-root "$PWD"
python3 scripts/install.py hooks --hosts auto --scope project --project-root "$PWD" --hook-profile startup-only

# Install lifecycle integration globally
python3 scripts/install.py hooks --hosts auto --scope user --hook-profile startup-only

# Check what would/does apply
python3 scripts/install.py status --hosts auto --scope project --project-root "$PWD"
```

Choose the hook profile from the user's intent:

- automatic startup context, recovery, or low overhead means `startup-only`;
- checkpoint reminders, changed-work enforcement, or every-turn enforcement means `full`;
- if the user only asks to “add hooks,” prefer `startup-only` and state that `full` is available for reminders.

The CLI keeps `full` as its no-flag default for backward compatibility. Always pass the selected profile explicitly when acting through this skill. Re-running the installer safely switches profiles and preserves unrelated hooks.

After installation, report: repository root, selected scope and hook profile, detected/configured hosts, files created or modified, backups created, activation/trust steps still required, and whether `.agent/project-context.json` is initialized. Existing host configuration must be preserved; malformed configuration must be refused rather than overwritten.

The capability-driven adapter model is documented in `references/hooks.md` and `ARCHITECTURE.md`.

## Optional stop-hook response

If a lifecycle hook reports that repository state changed without a matching project-context event:

1. append a meaningful observation/handoff if durable context changed; or
2. if the turn truly contains no durable project knowledge, explicitly acknowledge that with:

   ```bash
   ctx skip --agent <host-name> --reason "Formatting-only / ephemeral / no durable project context"
   ```

Do not create filler observations merely to satisfy the hook.

## Detailed references

Load only when needed:

- `references/protocol.md` — schema semantics, record types, reflection coverage, supersession
- `references/retrieval.md` — query strategy and token budgets
- `references/logging-policy.md` — what to record and how much detail to preserve
- `references/hooks.md` — lifecycle integration and host-specific behavior
- `references/hosts.md` — verified first-party host compatibility sources
- `ARCHITECTURE.md` — full design and installation model

## Safety

Never write secrets, credentials, access tokens, `.env` contents, private keys, complete transcripts, or large raw command outputs into project context.

Record safe conclusions and concise evidence instead.

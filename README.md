# project-context

`project-context` is a portable, file-based memory layer for coding agents. It lets you move between Claude Code, Codex, Grok, Cursor, Pi, and other harnesses without losing project decisions, failed approaches, verified findings, or the exact point where work stopped.

Every harness reads and writes the same append-only JSONL ledger. No database, vector store, background model, or hosted service is required.

[Explore the interactive project overview](https://project-context-mu.vercel.app) or [download the latest release](https://github.com/gabros20/project-context/releases/latest).

> [!NOTE]
> The design borrows Observational Memory's observation/reflection split, but keeps semantic checkpoints agent-authored so it can work across unrelated agent runtimes.

## Quick start

Requirements: Python 3.10+ and Git.

```bash
curl -fsSL https://project-context-mu.vercel.app/install.sh | sh

cd /path/to/your/repository
ctx init --instructions
python3 ~/.agent-skills/project-context/scripts/install.py hooks \
  --hosts auto --scope project --project-root "$PWD"
ctx doctor
```

The bootstrap downloads the pinned `v0.4.0` release into a temporary directory and delegates to the repository's installer. The installer keeps one canonical copy in `~/.agent-skills/project-context`, exposes it through each detected harness's skill directory, and creates a `ctx` launcher in `~/.local/bin` on Unix-like systems.

Windows PowerShell:

```powershell
irm https://project-context-mu.vercel.app/install.ps1 | iex
```

If `ctx` is not found after installation, add the launcher directory to your shell path:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

If automatic detection finds no host, replace `--hosts auto` with a comma-separated selection such as `--hosts claude,codex`, or use `--hosts all`.

## Use it from an agent

Invoke the skill without additional instructions to checkpoint the current session. The agent reviews its work, chooses an observation, handoff, or reflection, and appends the appropriate durable record.

| Harness | Invocation |
|---|---|
| Claude Code | `/project-context` |
| Codex | `$project-context` |
| Grok Build | `/project-context` |
| OpenCode | `/project-context` installer shim |
| Cursor CLI | `/project-context` |
| Factory Droid | `/project-context` |
| Pi / pi-mono | `/skill:project-context` |
| Google Antigravity | Ask it to use `project-context` |
| Hermes Agent | `/project-context` |
| OpenClaw | `/project-context` |

You can also narrow or force the checkpoint:

```text
/project-context auth
/project-context handoff
/project-context reflect the API work
```

Exact syntax and activation requirements are available from the installed package:

```bash
python3 ~/.agent-skills/project-context/scripts/install.py status \
  --hosts all --scope project --project-root "$PWD"
```

## How it works

```text
Claude / Codex / Grok / Cursor / Pi / other harness
                         │
                         ▼
              project-context skill
              chooses semantic content
                         │
                         ▼
                       ctx
             validates, timestamps, locks
                         │
                         ▼
          .agent/PROJECT_CONTEXT.jsonl
             append-only shared ledger
                         │
                         ▼
        bounded scope/path-aware retrieval
                         │
                         ▼
              next session or harness
```

The ledger uses three record types:

| Record | Purpose |
|---|---|
| Observation | One coherent unit of durable work: outcome, rationale, attempts, learnings, changes, and verification. |
| Handoff | The continuation frontier for unfinished or non-obvious work. |
| Reflection | A scope-aware consolidation of older records without rewriting or deleting history. |

Host adapters only translate native skill discovery and lifecycle events into `ctx` operations. The memory format and retrieval behavior remain host-independent.

## Everyday commands

| Command | Purpose |
|---|---|
| `ctx startup` | Render bounded startup memory. |
| `ctx context --scope auth` | Retrieve a subsystem's reflection and relevant frontier. |
| `ctx context --path src/auth/session.ts` | Retrieve memory related to a path. |
| `ctx context --scope auth --explain` | Show why each record was selected. |
| `ctx decisions --scope auth` | Review decisions and rationale. |
| `ctx attempts --scope auth --outcome failed` | Find failed approaches before repeating them. |
| `ctx open --scope auth` | Show remaining work and open questions. |
| `ctx blockers` | Show recorded blockers. |
| `ctx latest 8` | Show the latest records. |
| `ctx validate` | Validate the complete ledger. |
| `ctx stats` | Show record and reflection statistics. |
| `ctx doctor` | Inspect repository, storage, adapters, invocation, and activation status. |

Agents normally create entries through the skill. For direct CLI use, pass semantic JSON:

```bash
printf '%s\n' '{
  "record_type": "observation",
  "importance": "high",
  "scope": ["auth"],
  "context": "Refresh-token concurrency requires a bounded previous-token grace period. Immediate invalidation caused legitimate concurrent refreshes to be rejected."
}' | ctx append --agent manual --input -
```

See [the complete observation example](examples/observation.json) and [reflection example](examples/reflection.json) for richer structured records.

## Storage

`ctx init` makes the sharing boundary explicit:

| Mode | Ledger location | Best for |
|---|---|---|
| `repo` | `.agent/PROJECT_CONTEXT.jsonl` | Agents working in one checkout. This is the default. |
| `git-common` | Git's common directory | Multiple worktrees belonging to one clone. |
| `external` | User-supplied absolute path | User-managed synchronization or storage outside the repository. |

Examples:

```bash
ctx init --storage git-common --instructions
ctx init --storage external --storage-path /absolute/path/context.jsonl --instructions
ctx init --storage repo --tracking ignored --instructions
```

Repository storage has an independent tracking policy: `unmanaged` (default), `ignored`, or `versioned`. Separate clones and machines still require Git or another synchronization mechanism; `project-context` does not silently sync data.

## Optional checkpoint enforcement

Lifecycle adapters can detect when a session reaches a completion boundary without a durable checkpoint.

| Gate | Behavior |
|---|---|
| `off` | No Stop gate; explicit skill invocation drives checkpointing. Default. |
| `changed-work` | Request a checkpoint when Git state changed during the turn. |
| `every-turn` | Require an append or explicit skip after every completed turn, including reasoning-only work. |

```bash
ctx init --checkpoint-gate changed-work --instructions
ctx due --json
ctx skip --agent codex --reason "Formatting-only; no durable project knowledge"
```

Checkpoint enforcement degrades according to each harness's actual hook capabilities. Some adapters can block or continue a turn; others can only inject context or observe lifecycle boundaries. See the [host capability matrix](references/hooks.md).

## Installation and safety

Project-scoped lifecycle installation is the recommended default:

```bash
python3 ~/.agent-skills/project-context/scripts/install.py hooks \
  --hosts auto --scope project --project-root "$PWD"
```

User-wide installation is explicit:

```bash
python3 ~/.agent-skills/project-context/scripts/install.py hooks \
  --hosts auto --scope user
```

The installer:

- refuses malformed or non-object JSON configuration;
- preserves unrelated host settings and hook groups;
- creates a stable `*.project-context.bak` before first modification;
- writes atomically and is idempotent;
- never lets project scope modify user-level hooks;
- reports host trust or plugin activation that still requires user action.

See [INSTALL.md](INSTALL.md) for paths, scope rules, activation details, and the complete adapter matrix.

## What belongs in memory

Record durable project knowledge: behavior changes, architectural decisions, important constraints, debugging discoveries, failed approaches, verification, blockers, and continuation state.

Do not use the ledger for tool-call narration, entire transcripts, large raw outputs, secrets, credentials, tokens, private keys, or `.env` contents. Store safe conclusions and concise evidence instead.

## Design documentation

- [Architecture](ARCHITECTURE.md) — system boundaries, lifecycle model, retrieval, and concurrency.
- [ADR-001](docs/decisions/001-portable-observational-ledger.md) — why the project uses an agent-authored ledger inspired by Observational Memory.
- [Protocol](references/protocol.md) — record semantics, validation, supersession, and reflection coverage.
- [Retrieval](references/retrieval.md) — scope/path selection and token budgeting.
- [Logging policy](references/logging-policy.md) — what to preserve and what to omit.
- [Host sources](references/hosts.md) — first-party compatibility evidence.
- [Changelog](CHANGELOG.md) — release history.

## Development

The runtime and installer use only the Python standard library.

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/ctx.py scripts/install.py scripts/check_release.py
git diff --check
```

Current package version: `0.4.0`. Ledger protocol version: `1`.

Maintainers: see [RELEASING.md](RELEASING.md) for the signed-tag release process.

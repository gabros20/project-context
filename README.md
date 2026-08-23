# project-context

`project-context` gives coding agents a shared project notebook. It saves decisions, failed approaches, test results, and unfinished work in one JSONL file so you can switch between Claude Code, Codex, Grok, Cursor, Pi, and other tools without explaining the project again.

Every supported agent reads and writes the same file. There is no database, background model, or hosted service.

[Explore the interactive project overview](https://project-context-mu.vercel.app) or [download the latest release](https://github.com/gabros20/project-context/releases/latest).

> [!NOTE]
> The observation and reflection idea comes from Observational Memory. Here, the coding agent writes each useful checkpoint so unrelated tools can share the same file.

## Quick start

Requirements: Python 3.10+ and Git.

```bash
curl -fsSL https://project-context-mu.vercel.app/install.sh | sh

cd /path/to/your/repository
ctx init --instructions
ctx doctor
```

This installs the skill and the `ctx` command. It does not install hooks. Start here, then add hooks only if you want automatic startup context or checkpoint reminders.

The bootstrap downloads the pinned `v0.4.0` release into a temporary directory. The installer keeps one copy in `~/.agent-skills/project-context`, links it into each detected agent's skill directory, and creates a `ctx` launcher in `~/.local/bin` on Unix-like systems.

Windows PowerShell:

```powershell
irm https://project-context-mu.vercel.app/install.ps1 | iex
```

If `ctx` is not found after installation, add the launcher directory to your shell path:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

If automatic detection finds no agent tool, replace `--hosts auto` with a comma-separated selection such as `--hosts claude,codex`, or use `--hosts all`.

## What you get

- **A handoff that survives the chat.** Run the skill before switching tools or ending a session. The next agent can see what changed, why it changed, what failed, what passed, and what remains.
- **One local file.** Memory lives in `.agent/PROJECT_CONTEXT.jsonl`. You can read it, review it in Git, ignore it, or place it in Git's common directory for shared worktrees.
- **No automatic transcript logging.** The project stores useful engineering conclusions, not every prompt, command, or tool call.
- **Targeted recall.** Agents can retrieve notes for one scope or file instead of loading the complete history.
- **Optional hooks.** Hooks can load recent memory at session start and remind an agent to checkpoint. They never call a background model or write an observation by themselves.
- **The same format across ten agent tools.** Host-specific adapters are replaceable. The JSONL format and `ctx` command stay the same.

## When it runs and what it costs

The default setup is skill-only. Nothing runs on every prompt unless you install hooks.

| Setup | What runs | When the ledger is written |
|---|---|---|
| Skill installed, repo not initialized | Nothing | Never |
| Skill-only | The skill runs when you invoke it | Once per invocation, or it records an explicit skip |
| Hooks with gate `off` | Startup loading plus local prompt and stop checks | Never automatically |
| Hooks with `changed-work` | A Git baseline at prompt start and a check at completion | The agent is reminded when Git changed and no checkpoint exists |
| Hooks with `every-turn` | A check after every completed turn | Every turn needs a checkpoint or explicit skip |

Hooks run local Python, Git, and file operations. They do not make their own model request. With hooks installed, session start can inject up to 2,200 tokens of relevant memory. A compaction refresh is capped at 1,200 tokens. An explicit targeted query is capped at 3,000 tokens. Stored entries use no model tokens until an agent retrieves them.

Loading the full skill is roughly 2,300 input tokens. The repository instruction block is roughly 400 tokens. A routine checkpoint is usually 100 to 300 words, or roughly 150 to 500 generated tokens including its structured fields. These are approximate numbers because `ctx` estimates tokens from character count rather than using a tokenizer.

One latency tradeoff is worth knowing. The current `turn-start` hook runs `git rev-parse` and `git status --untracked-files=all` on each submitted prompt, even when the checkpoint gate is `off`. That is usually quick, but a large repository with many untracked files may notice it. Use skill-only mode for the lowest overhead.

Recommended starting point: use skill-only mode and invoke `project-context` after a meaningful milestone, before changing agent tools, or when leaving unfinished work. Add the `changed-work` gate if you often forget. `every-turn` is meant for strict capture and will feel noisy in normal development.

## Use it from an agent

Invoke the skill without additional instructions to save the useful parts of the current session. The agent chooses an observation, handoff, or reflection and appends one record.

| Agent tool | Invocation |
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
Claude / Codex / Grok / Cursor / Pi / other agent
                         │
                         ▼
              project-context skill
               writes a useful note
                         │
                         ▼
                       ctx
             validates, timestamps, locks
                         │
                         ▼
          .agent/PROJECT_CONTEXT.jsonl
              shared project file
                         │
                         ▼
          query by scope or file path
                         │
                         ▼
               next session or agent
```

The ledger uses three record types:

| Record | Purpose |
|---|---|
| Observation | One completed unit of work: what changed, why, what failed, and what the tests showed. |
| Handoff | The current state and exact next steps for unfinished work. |
| Reflection | A current summary of older notes for one part of the project. The original entries remain unchanged. |

Each adapter connects an agent tool's own skill and hook system to `ctx`. Every agent still reads and writes the same JSONL format.

## Everyday commands

| Command | Purpose |
|---|---|
| `ctx startup` | Load the most relevant notes for a new session. |
| `ctx context --scope auth` | Retrieve current and recent authentication notes. |
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

Agents normally create entries through the skill. For direct CLI use, pass structured JSON:

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

`ctx init` lets you choose where the file lives:

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

Repository storage has three tracking options: `unmanaged` (default), `ignored`, or `versioned`. Separate clones and machines still need Git or another way to synchronize the file. `project-context` does not sync data by itself.

## Optional checkpoint reminders

Hooks can notice when an agent finishes a turn without saving a checkpoint.

| Gate | Behavior |
|---|---|
| `off` | Never require a checkpoint. Invoke the skill yourself. This is the default. |
| `changed-work` | Ask for a checkpoint when Git changed during the turn. |
| `every-turn` | Require an append or explicit skip after every completed turn, including reasoning-only work. |

```bash
ctx init --checkpoint-gate changed-work --instructions
ctx due --json
ctx skip --agent codex --reason "Formatting-only; no durable project knowledge"
```

Agent tools expose different hook controls. Some can pause completion and ask for a checkpoint. Others can only load notes or report that a checkpoint is due. See the [agent support table](references/hooks.md).

## Installation and safety

Add hooks to one project:

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
- creates a stable `*.project-context.bak` before the first change;
- writes atomically and is idempotent;
- never lets project scope modify user-level hooks;
- reports host trust or plugin activation that still requires user action.

See [INSTALL.md](INSTALL.md) for paths, scope rules, activation details, and the complete adapter matrix.

## What belongs in memory

Record project knowledge another developer would need: behavior changes, architectural decisions, constraints, debugging discoveries, failed approaches, test results, blockers, and next steps.

Do not use the ledger for tool-call narration, entire transcripts, large raw outputs, secrets, credentials, tokens, private keys, or `.env` contents. Store safe conclusions and concise evidence instead.

## Design documentation

- [Architecture](ARCHITECTURE.md): system boundaries, hooks, retrieval, and concurrency.
- [ADR-001](docs/decisions/001-portable-observational-ledger.md): why the project uses an agent-written log inspired by Observational Memory.
- [Protocol](references/protocol.md): record fields, validation, corrections, and reflection coverage.
- [Retrieval](references/retrieval.md): scope and path queries plus token budgets.
- [Logging policy](references/logging-policy.md): what to save and what to leave out.
- [Agent sources](references/hosts.md): first-party compatibility evidence.
- [Changelog](CHANGELOG.md): release history.

## Development

The runtime and installer use only the Python standard library.

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/ctx.py scripts/install.py scripts/check_release.py
git diff --check
```

Current package version: `0.4.0`. Ledger protocol version: `1`.

Maintainers: see [RELEASING.md](RELEASING.md) for the signed-tag release process.

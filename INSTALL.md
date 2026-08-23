# Universal installation

## 1. Install the portable skill/runtime

macOS or Linux:

```bash
curl -fsSL https://project-context-mu.vercel.app/install.sh | sh
```

Windows PowerShell:

```powershell
irm https://project-context-mu.vercel.app/install.ps1 | iex
```

The bootstrap downloads the pinned `v0.4.0` release into a temporary directory, invokes the same `scripts/install.py` shipped in that release, and removes the temporary checkout. It requires Python 3.10+ and Git.

Inspect the bootstrap without executing it:

```bash
curl -fsSL https://project-context-mu.vercel.app/install.sh
```

Pass installer options after `sh -s --`:

```bash
curl -fsSL https://project-context-mu.vercel.app/install.sh | \
  sh -s -- --hosts all --hooks
```

To deliberately test another tag or branch, set `PROJECT_CONTEXT_VERSION` for the shell receiving the script:

```bash
curl -fsSL https://project-context-mu.vercel.app/install.sh | \
  PROJECT_CONTEXT_VERSION=main sh
```

Manual source installation remains available:

```bash
git clone --branch v0.4.0 --depth 1 \
  https://github.com/gabros20/project-context.git
cd project-context
python3 scripts/install.py install --hosts auto
```

This keeps one canonical copy at:

```text
~/.agent-skills/project-context/
```

and creates compatible links/copies for detected hosts. The installer also creates `~/.local/bin/ctx` when possible.

To install skill visibility for every supported host explicitly:

```bash
python3 scripts/install.py skills --hosts all --scope user
```

## 2. Initialize a repository

```bash
cd /path/to/repo
ctx init --instructions
```

Storage/checkpoint examples:

```bash
# Share one ledger across worktrees in this clone
ctx init --storage git-common --instructions

# Require a checkpoint only after changed Git state
ctx init --checkpoint-gate changed-work --instructions

# Strictly require append or skip after every completed turn
ctx init --checkpoint-gate every-turn --instructions
```

Creates:

```text
.agent/project-context.json
.agent/PROJECT_CONTEXT.jsonl
.agent/PROJECT_CONTEXT.schema.json
```

and appends a marker-delimited bootstrap block to `AGENTS.md`. Existing `AGENTS.md` and `CLAUDE.md` are backed up once and preserved; Claude receives an `@AGENTS.md` bridge only when one is not already present.

## 3. Install lifecycle integration at the scope you want

Project-only (recommended default):

```bash
python3 ~/.agent-skills/project-context/scripts/install.py hooks \
  --hosts auto --scope project --project-root "$PWD"
```

User/global:

```bash
python3 ~/.agent-skills/project-context/scripts/install.py hooks \
  --hosts auto --scope user
```

Specific hosts:

```bash
python3 scripts/install.py hooks \
  --hosts claude,codex,cursor,opencode,pi \
  --scope project --project-root "$PWD"
```

The skill itself understands natural requests such as “add the project-context lifecycle hooks to this project” and will run the same installer.

## 4. What gets written

Project adapters:

```text
Claude Code  .claude/settings.json
Codex        .codex/hooks.json
Grok Build   .grok/hooks/project-context.json
OpenCode     .opencode/plugins/project-context.js
             .opencode/commands/project-context.md
Cursor CLI   .cursor/hooks.json
Droid        .factory/hooks.json
Pi           .pi/extensions/project-context.ts
Antigravity  .agents/hooks.json
Hermes       .hermes/plugins/project-context/
OpenClaw     hooks/project-context/
```

User adapters use each host's documented personal configuration directory. See `references/hooks.md` for the complete matrix.

## 5. Safety around existing configuration

Existing configuration is not blindly overwritten.

- JSON is parsed before modification; malformed/non-object JSON is refused.
- Unrelated keys and hook groups are preserved.
- A one-time exact original is written beside an existing file as `*.project-context.bak` before the first modification.
- Writes are atomic.
- Repeated installs are idempotent.
- Project scope never modifies user/global hook files.
- Generated plugin/extension files are backed up before replacement.

First-time JSON merge may normalize whitespace/indentation, while preserving values.

## 6. Host trust/activation

The installer does not bypass host security controls. Depending on the host you may still need to trust a workspace/project hook or enable a plugin/hook pack. Run:

```bash
python3 scripts/install.py status --hosts auto --scope project --project-root "$PWD"
```

and follow the printed host-specific activation/trust note.

`--activate` performs only documented best-effort enable commands where safe and available; it does not fake trust decisions.

## 7. Checkpoint enforcement starts disabled

Default repo config:

```json
"checkpoint": {"stop_gate": "off"},
"storage": {"mode": "repo", "tracking": "unmanaged"}
```

Choose `changed-work` or `every-turn` later if desired. Legacy `hooks.stop_check: true` is still accepted as `changed-work`. Even with lifecycle adapters installed, semantic observations remain agent-authored.

## 8. Verification

```bash
ctx doctor
ctx validate
python3 scripts/install.py detect
python3 scripts/install.py status --hosts all --scope project --project-root "$PWD"
```

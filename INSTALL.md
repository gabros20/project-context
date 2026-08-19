# Universal installation

## 1. Install the portable skill/runtime

Extract the package, enter `project-context-v0.3.0/`, then run:

```bash
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

## 7. Stop enforcement starts disabled

Default repo config:

```json
"hooks": {"stop_check": false}
```

Enable later if desired. Even with lifecycle adapters installed, semantic observations remain agent-authored.

## 8. Verification

```bash
ctx doctor
ctx validate
python3 scripts/install.py detect
python3 scripts/install.py status --hosts all --scope project --project-root "$PWD"
```

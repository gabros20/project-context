# project-context universal v0.3.0

Portable Agent Skill + deterministic `ctx` runtime for append-only shared episodic project memory across multiple coding-agent harnesses.

Supported adapter targets:

- Claude Code
- Codex
- Grok Build
- OpenCode
- Cursor CLI
- Factory Droid CLI
- Pi / pi-mono
- Google Antigravity CLI
- Hermes Agent
- OpenClaw

The **memory protocol is host-independent**. Host adapters only translate native skill discovery, project instruction files, and lifecycle events into the same `ctx` operations.

Read [ARCHITECTURE.md](ARCHITECTURE.md) first.

## Fast start

Install one canonical personal copy and expose it to detected hosts:

```bash
python3 scripts/install.py install --hosts auto
```

Initialize a repo:

```bash
cd /path/to/repo
ctx init --instructions
```

Install lifecycle adapters for **this project**:

```bash
python3 ~/.agent-skills/project-context/scripts/install.py hooks \
  --hosts auto --scope project --project-root "$PWD"
```

Or ask a supported coding agent naturally:

> Add the project-context lifecycle hooks to this project.

The skill instructs the agent to run the bundled safe installer and report the result.

Inspect support/installation:

```bash
python3 scripts/install.py detect
python3 scripts/install.py status --hosts all --scope project --project-root "$PWD"
ctx doctor
```

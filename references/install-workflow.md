# Installing lifecycle integration


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


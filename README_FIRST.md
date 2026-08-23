# Project Context v0.4.0

This is a plain download bundle. The actual Agent Skill is inside `project-context-v0.4.0/` so the outer ZIP is not itself treated as a skill card.

## Quick start

From any directory with Python 3.10+ and Git:

```bash
curl -fsSL https://project-context-mu.vercel.app/install.sh | sh
```

If you already downloaded and extracted this release bundle:

```bash
cd project-context-v0.4.0
python3 scripts/install.py install --hosts auto
```

Initialize a repository:

```bash
cd /path/to/repo
ctx init --instructions
```

Install lifecycle integration only for that repository:

```bash
python3 ~/.agent-skills/project-context/scripts/install.py hooks \
  --hosts auto --scope project --project-root "$PWD"
```

Or tell an agent with the skill installed:

> Add the project-context lifecycle hooks to this project.

See `ARCHITECTURE.md`, `docs/decisions/`, and `project-context-v0.4.0/INSTALL.md`.

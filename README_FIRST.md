# Project Context Universal v0.3.0

This is a plain download bundle. The actual Agent Skill is inside `project-context-v0.3.0/` so the outer ZIP is not itself treated as a skill card.

## Quick start

```bash
cd project-context-v0.3.0
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

See `PROJECT_CONTEXT_UNIVERSAL_ARCHITECTURE.md` and `project-context-v0.3.0/INSTALL.md`.

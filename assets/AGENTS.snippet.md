## Shared project context

This repository uses the `project-context` Agent Skill and `.agent/PROJECT_CONTEXT.jsonl` as append-only shared memory across coding-agent sessions and harnesses.

- Before meaningful work, use the `project-context` skill. A lifecycle adapter may already have injected a bounded startup packet; do not reread the full log by default.
- Before modifying a known subsystem/path, retrieve targeted context with `ctx context --scope <scope>` or `ctx context --path <path>`.
- After a coherent unit of durable work, append a rich observation covering what happened, why, decisions/alternatives, attempts that worked or failed, reusable learnings, verification, and current state.
- Use `ctx handoff` when work is unfinished or another session needs explicit continuation state.
- Create reflections periodically so future agents can load durable state plus only the recent tail.
- Never manually rewrite historical JSONL entries. Corrections are new entries linked by supersession/resolution.
- Never store secrets, `.env` contents, credentials, full transcripts, or large raw command output in project context.
- If asked to install/check project-context lifecycle hooks, use the bundled skill installer. “This project/repo/here” means project scope; never silently install global hooks.

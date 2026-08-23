# Changelog

## 0.4.0 - 2026-08-22

### Added

- Scope-aware, source-backed reflection coverage and inherited `related_paths`.
- Priority-aware context budgeting with latest-handoff preservation and `ctx context --explain`.
- `ctx due --json` and `off`, `changed-work`, and `every-turn` checkpoint gates.
- Repository, Git-common, and external ledger storage modes with explicit tracking policy.
- Capability-driven host manifest containing invocation, lifecycle, trust, activation, and evidence metadata.
- OpenCode `/project-context` command shim, adapter contract tests, concurrency tests, and ADR-001.

### Fixed

- Selected reflections no longer reappear in their own unreflected frontier.
- Reflections for one scope no longer hide history in another scope.
- Path-targeted retrieval can find reflections through direct and supporting-entry paths.
- Small context budgets retain the newest handoff/frontier instead of favoring older entries.
- Nested record validation now enforces required fields, enum values, paths, and coverage references.
- Reflection coverage calculation and append are one locked transaction.
- OpenClaw's generated bootstrap adapter now imports `homedir`.

### Changed

- Product language now describes a portable agent-authored ledger inspired by Observational Memory rather than behaviorally universal host automation.
- `.agents/skills` is the preferred shared discovery path where officially supported.
- Legacy `hooks.stop_check: true` is mapped to `checkpoint.stop_gate: changed-work`.
- Package version is 0.4.0; ledger protocol remains version 1 and existing logs require no rewrite.

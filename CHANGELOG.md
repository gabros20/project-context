# Changelog

## 0.5.0 - 2026-08-23

### Added

- `startup-only` and `full` hook profiles for project and user lifecycle installation.
- Safe profile switching that replaces project-context-managed hooks while preserving unrelated host configuration.
- Profile-specific generated adapters for OpenCode, Pi, Hermes, and OpenClaw.
- ADR-002 documenting the separation between automatic context recovery and checkpoint enforcement.

### Changed

- The bundled skill now prefers `startup-only` when a user asks for hooks without requesting checkpoint reminders.
- Runtime and website documentation now explain prompt frequency, host exceptions, latency, and token behavior for both profiles.
- Package version is 0.5.0; ledger protocol remains version 1 and existing logs require no rewrite.

### Fixed

- Session and turn start skip Git fingerprinting when the checkpoint gate is `off`.
- Gate-off turn start no longer writes transient per-turn state.

## 0.4.0 - 2026-08-23

### Added

- Scope-aware, source-backed reflection coverage and inherited `related_paths`.
- Priority-aware context budgeting with latest-handoff preservation and `ctx context --explain`.
- `ctx due --json` and `off`, `changed-work`, and `every-turn` checkpoint gates.
- Repository, Git-common, and external ledger storage modes with explicit tracking policy.
- Capability-driven host manifest containing invocation, lifecycle, trust, activation, and evidence metadata.
- OpenCode `/project-context` command shim, adapter contract tests, concurrency tests, and ADR-001.
- Version-pinned one-command bootstrap installers for POSIX shells and Windows PowerShell.
- A tag-triggered, contract-checked GitHub release workflow and maintainer release guide.
- The responsive project website, SVG identity, and explanatory memory-flow visualizations.

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

# ADR-002: Separate startup recovery from checkpoint enforcement

## Status

Accepted

## Date

2026-08-23

## Context

Lifecycle adapters originally installed every available event: session start, prompt baseline, compaction, Stop, and session end. This made one installation capable of both automatic context recovery and missing-checkpoint reminders.

The default checkpoint gate is `off`. In that state the prompt hook could not produce a reminder, yet `turn-start` still calculated a Git fingerprint and wrote transient state for every prompt. Users who only wanted a new agent to load the shared notebook paid for lifecycle work they did not use. Large repositories with many untracked files made that cost easier to notice.

The project must keep existing installations compatible, preserve unrelated host configuration, and support harnesses with different startup APIs.

## Decision

Expose two installer profiles through `--hook-profile`:

- `startup-only` installs the minimum lifecycle surface needed for startup context and compaction recovery where supported;
- `full` also installs prompt baselines, Stop checks, and session-boundary tracking.

Keep `full` as the default so existing commands retain their behavior. Recommend `startup-only` to users who want automatic recovery without checkpoint enforcement.

Make profile switching reconciliatory. Before adding the selected profile, remove only commands that match project-context's normalized hook command for that host. Preserve unrelated settings, hooks, and mixed hook groups.

Make `turn-start` return the host's neutral response immediately when `checkpoint.stop_gate` is `off`, before Git fingerprinting or transient state writes. This protects existing full-profile installations that have not switched profiles.

Capability degradation still applies. Antigravity has no separate session-start injection event, so `startup-only` retains its `PreInvocation` bridge. Pi and Hermes retain an in-process first-turn callback but do not spawn the project-context runtime on later turns.

## Alternatives Considered

### Change the default profile to `startup-only`

- Pros: lowest overhead for new installations.
- Cons: an existing installation command would silently stop installing checkpoint reminders.
- Rejected because lifecycle enforcement is observable behavior. A future major release may reconsider the default.

### Keep one profile and optimize only `turn-start`

- Pros: no new installer option.
- Cons: every prompt would still launch a local hook process even when the gate is off.
- Rejected because startup recovery and checkpoint enforcement are independent user needs.

### Store the profile in repository memory configuration

- Pros: one setting could drive all hosts.
- Cons: hook installation is host and scope configuration, while the ledger config is repository runtime policy. A runtime setting cannot remove a host hook that must run before the setting can be read.
- Rejected to keep installation state at the host edge.

### Install separate startup and enforcement packages

- Pros: each package has a narrow purpose.
- Cons: duplicates adapters, commands, backups, and migration logic.
- Rejected in favor of one installer with an explicit profile.

## Consequences

- Users can get automatic session recovery with virtually no per-turn project-context work on hosts that expose a startup event.
- Checkpoint gates require the `full` profile to enforce reminders at host completion boundaries.
- Re-running the installer is the supported way to switch profiles.
- The ledger format and protocol version do not change.
- Host limitations remain visible rather than being hidden behind a false cross-harness guarantee.

# Protocol reference

Read this when constructing rich records, reflections, supersession links, or troubleshooting schema validation.

## Record types

### observation

Rich episodic memory for one coherent unit of durable work.

Required semantic fields supplied by the agent:

- `record_type: observation`
- `importance`
- `scope`
- `context`

Optional structured sections:

- `task`
- `decisions`
- `attempts`
- `learnings`
- `changes`
- `related_paths` for paths affected by the durable conclusion even when they are not dirty
- `verification`
- `current_state`
- `related_entries`
- `tags`

### handoff

Frontier state for continuation. Same general shape as an observation, but `current_state` is required and should explicitly describe remaining work and next steps.

### reflection

Consolidated durable understanding derived from older observations/handoffs.

Required semantic fields:

- `record_type: reflection`
- `importance`
- `scope`
- `context`
- `durable_state`
- `coverage` (boundaries may be auto-filled by `ctx reflect`)

## Attempts

Allowed outcomes:

- `worked`
- `failed`
- `partial`
- `inconclusive`
- `abandoned`

Preserve why the approach produced that outcome and the reusable learning. Include evidence when it materially prevents repeated work.

## Learnings

Allowed types:

- `fact`
- `invariant`
- `constraint`
- `convention`
- `gotcha`
- `hypothesis`
- `open_question`

Confidence:

- `confirmed`
- `likely`
- `tentative`

Do not promote a hypothesis to a fact merely because it is old.

## Supersession

When a previous statement is no longer true, append a new entry and put the replaced `entry_id` under:

```json
{"related_entries":{"supersedes":["old-entry-id"]}}
```

When a new event completes an old open item, use `resolves`. Use `related` for non-hierarchical relationships.

## Reflection coverage

A reflection may include:

```json
{
  "coverage": {
    "from_entry_id": "...",
    "through_entry_id": "...",
    "supporting_entry_ids": ["...", "..."]
  }
}
```

`through_entry_id` means the reflection has considered history through that point. `supporting_entry_ids` identifies the entries that materially support the reflected durable state.

Automatic coverage is scoped. The CLI finds the previous reflection whose scope overlaps the new reflection, then covers only subsequent observations and handoffs in the new reflection's scope. An empty scope is project-wide. Coverage calculation and append happen under the same ledger lock.

`coverage.scope` records the scope used for the calculation. `through_entry_id` is a scoped watermark, never permission to hide unrelated subsystem history.

New reflections require at least one unreflected source record. `ctx reflect --allow-empty-coverage` is reserved for a deliberate initial baseline.

Do not claim a source is represented by a reflection if its unique durable meaning was omitted.

The current implementation never deletes covered observations, so coverage mistakes are recoverable.

## Change attribution

`changes.capture` distinguishes agent-authored file attribution from a repository snapshot:

- `agent-authored` means the semantic payload intentionally attributed the listed files;
- `git-snapshot` means `ctx` filled the list from the dirty worktree and the files may include concurrent or pre-existing changes.

## Run records

A record may describe one whole run of another tool rather than one session's work: `agent.name` is the tool (`orchestrate`), `agent.session_id` is the run id, and `task.id` repeats it so both `ctx context --session` and `ctx query --task` find it. Such a record carries the run's decisions (with rationale, or an explicit "not recorded"), the attempts that actually ran, learnings, verification and `current_state`; it never carries raw logs or report bodies, only their paths.

## Metadata owned by ctx

The CLI derives and overwrites:

- `version`
- `timestamp`
- `entry_id`
- `agent`
- `repository`

The agent should provide semantic content rather than reimplementing metadata collection.

## Semantic input and validation

`ctx schema` describes agent-authored input; `ctx schema --stored` includes ctx-owned metadata. `ctx schema --section verification` is the smallest field reference. `ctx template <type> --minimal` returns valid starter JSON. Verification uses `{ "check": "...", "outcome": "passed", "details": "..." }`; allowed outcomes are passed, failed, partial, not_run, inconclusive. Runtime validation uses the bundled schema's supported constructs; errors identify JSON Pointer and rule. Append commands also accept `--json-errors` for structured diagnostics on stderr. Extensions are allowed, with warnings for likely misspellings.

`ctx append --check` validates without a ledger or runtime write. `--idempotency-key` makes identical semantic retries return the original entry; different payloads using that key are rejected. Metadata collection is not an identity key. Prefer explicit `--session-id` or PROJECT_CONTEXT_SESSION_ID; multiple active sessions of one host will not silently borrow a shared host pointer.

A whole-entry resolves relationship clears only that source's current_state in the current projection. `source-id#/current_state/blockers/0` removes one array item; indexes refer to the immutable source. Whole-entry supersession removes the source from current retrieval. History and show retain originals. Relationships must reference existing records; this also prevents future-reference cycles. Item pointers use current_state field names and array indexes, not arbitrary document edits.

Reflection suppression uses explicit supporting IDs plus applicable coverage scope, not a global through_entry_id cutoff. Mixed-scope source records remain visible for their uncovered scopes. Previous reflections remain available unless superseded. New explicit empty coverage is rejected unless deliberately allowed. Legacy watermark-only records remain readable without granting unproven coverage.

## Writable runtime

Locks live in `.ctx-locks` next to the canonical ledger so all cooperating processes lock the same file, including git-common storage. Runtime state defaults to `.agent/runtime/<repo-key>`; configure `runtime.directory` in repository config or PROJECT_CONTEXT_RUNTIME_DIR for a writable alternative. Configure all cooperating harnesses consistently. Runtime/lock paths are excluded from Git checkpoint fingerprints. A durable append returns success even if its ancillary runtime update fails, with a warning and the persisted entry ID.

`doctor --host <host> --json --self-test` validates the local ledger and bounded packet and reports project hook presence, writable paths, and emission metadata. Emitted does not mean acknowledged by the host. Delivery state is session-local; compaction requests a fresh baseline even when content is unchanged. Existing global-cache runtime state is ephemeral and is not migrated; durable records remain compatible.

When upgrading from0.6, finish old agent sessions before allowing concurrent writers: new locks are ledger-adjacent, while older installations use home-cache locks. Do not run mixed runtime versions against the same ledger concurrently. No historical JSONL rewrite is required. Reinstall hooks through the bundled installer to pick up bounded adapter subprocesses.

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

## Metadata owned by ctx

The CLI derives and overwrites:

- `version`
- `timestamp`
- `entry_id`
- `agent`
- `repository`

The agent should provide semantic content rather than reimplementing metadata collection.

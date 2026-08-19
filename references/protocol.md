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

Do not claim a source is represented by a reflection if its unique durable meaning was omitted.

The current implementation never deletes covered observations, so coverage mistakes are recoverable.

## Metadata owned by ctx

The CLI derives and overwrites:

- `version`
- `timestamp`
- `entry_id`
- `agent`
- `repository`

The agent should provide semantic content rather than reimplementing metadata collection.

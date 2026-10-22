# Retrieval strategy

Use one bounded request relevant to the current task. Prefer a packet already injected at startup over a redundant explicit startup call. Do not read full JSONL solely because it exists.

```sh
ctx context --path src/auth --path src/api --budget 1200
ctx context --query "Safari viewport mobile hero height" --budget 1200
ctx search "exact error message" --scope auth --budget 1000
ctx scopes
ctx show <entry-id> --section current_state
ctx context --scope auth --explain
```

Repeated paths are OR; different filter types are AND. Scope labels match exactly, case-insensitively. No-match responses suggest discovery without silently broadening filters. Search ranks fields locally with BM25, weighting declared paths, durable constraints, and current state. It uses no embedding provider, external service, or additional database. Rebuilds are unnecessary at current ledger sizes; benchmark before adding an index or embeddings.

Context defaults to current records. Superseded records are removed and explicitly resolved state is folded; use `context --history` or `search --history` to investigate earlier claims. `show` always expands the immutable source, so provenance remains accessible. A claim's age or shared scope does not establish resolution. Search scores indicate lexical relevance, not truth or verification confidence.

Packets select relevant reflections plus uncovered source records. Coverage is explicit and scope-sensitive; a docs reflection cannot discard auth history. For a multi-scope/global packet, a partial-scope reflection cannot hide the other parts of a mixed-scope observation. Legacy watermark-only coverage is treated conservatively. Older relevant reflections remain available until explicitly superseded.

Under budget pressure, brief cards retain current blockers, next steps and durable constraints before background prose, with `ctx show` expansion. `--explain` reports selection and budget omissions. Budgets are approximate characters/4, with a minimum400-character packet; they are not model-specific token counts. Unicode and JSON identifiers can tokenize differently.

Session defaults are2200 estimated tokens for startup,1200 after compaction,3000 for explicit retrieval. Increase explicit recall only when the missing material warrants it. Do not replace meaningful words with run-together shorthand to save tokens.

For one run use `ctx context --session <id>` or `--task <id>`. For focused fields use `ctx decisions`, `ctx attempts --outcome failed`, `ctx open`, or `ctx blockers`. Extractors prefer recent blocks when the budget is tight. Attempts fold identical approaches with identical outcomes; `--no-group` expands repeats.

## Reflection preparation

```sh
ctx stats
ctx reflect --prepare --scope auth --budget 2000
ctx reflect --prepare --scope auth --offset 4 --budget 2000
```

Preparation does not call a model or append a record. It returns the previous reflection, bounded source cards, and a template with explicit supporting IDs for the displayed source set. Read those sources before claiming coverage. Pagination can produce separate partial reflections. The CLI validates source existence and fills boundaries, but the agent owns semantic completeness and factual accuracy.

Stats reports uncovered work by scope and estimated volume. Appending produces a nonblocking reflection hint at uncovered-count milestones. There is no requirement to reflect after every command.

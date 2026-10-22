# Project-context agent usability review

Reviewed 2026-10-22 against the local v0.6.0 source. This is a review and implementation proposal, not an implementation. Existing modifications to site/index.html and untracked instruction files were preserved.

## Assessment

Keep the append-only ledger, local operation, explicit engineering rationale, bounded retrieval, and thin host adapters. The biggest opportunity is making saved knowledge reliably discoverable and actionable. Increasing storage detail or adding embeddings alone will not accomplish that.

Evidence includes source inspection of ctx.py, install.py, the schema, skill/references, adapter templates, tests, direct in-memory reproductions, and aggregate statistics from the Eagle website ledger. No live compatibility claim is made for every harness. The 33 existing tests pass with process-local Git signing disabled and a writable temporary cache. The initial run had 17 failures caused by inherited Git signing configuration, not established product failures.

## P0: Correct reflection coverage before improving search

Source: scripts/ctx.py:665 reflection_coverage; :1028 latest_reflection; :1033 select_context_entries; :1871 cmd_stats.

Reproduction: place an auth observation before a docs observation, followed by a docs-only reflection covering the docs observation. Unscoped select_context_entries chooses the docs reflection, starts the frontier after its watermark, and omits the older auth observation. The stored auth entry is intact, but the startup packet loses it. A new global reflection over the same history can fail with no unreflected records even though auth was never reflected. A single latest overlapping reflection is insufficient for a multi-scope/global view.

Implement explicit coverage of source entries, or per-scope frontiers with conservative treatment of mixed-scope records. Never remove an observation from a packet solely because an unrelated reflection is later. Preserve facts not actually represented by a selected reflection. Make stats calculate uncovered work by scope using the same coverage engine.

Acceptance: narrow, global, mixed-scope, path-filtered, and legacy-coverage tests demonstrate no unrelated knowledge disappears. Test partial coverage and multiple reflections. Do not use semantic similarity to decide that a reflection covers a fact.

## P0: Pack actionable fields before narrative

Source: scripts/ctx.py:879 format_entry; :1098 pack_context_packet; :999 blocks_with_budget.

Reproduction: a handoff with a long context and a short current_state.next_steps was packed into a 300-token budget. Historical background survived; the next action did not. Preserving an entry header is not sufficient to preserve its useful content. Reflection context can similarly consume its allocation before durable_state appears. Extractor commands also consume their selected blocks oldest-first, allowing verbose older entries to crowd out newer ones.

Implement field-aware cards. Reserve space for task/status, constraints, blockers, next actions, verification limits, and source IDs before clipping narrative. Prefer recent actionable extractor results under pressure. Offer a compact brief and an expansion command by entry ID. Keep chronological rendering where useful after priority selection. Include a short omitted-content indicator and exact expansion command.

Acceptance: at small budgets, the newest handoff's next action and blocker survive long background text. A reflection retains its constraints. Exact budget and Unicode-heavy cases are covered. Existing --explain should report field-level omissions as well as entry selection.

## P1: Discovery and lexical search, followed by optional hybrid retrieval

Source: scripts/ctx.py:781 matches_scope; :817 matches_path; :832 filter_entries; :1993 parser.

Scope matching is exact and case-insensitive. Path matching searches declared paths, not narrative. There is no free-text search command. A zero-match context packet still prints total repository entries and generic advice, which is easy to misinterpret. The Eagle corpus uses overlapping labels such as homepage, home-new, hero, and mobile. Guessing feedback failed to retrieve useful prior work.

Implement ctx search "mobile Safari hero height" with ranked snippets and source IDs; ctx scopes with counts and recent paths; explicit matched/selected/omitted counts; and zero-match suggestions with exact retry commands. Preserve strict scope/path filter semantics rather than silently broadening them. Support several --path arguments in one request. Add ctx show <entry-id> so the agent can expand one relevant hit cheaply.

Start with a rebuildable local lexical index, such as SQLite FTS where supported, or a dependency-light BM25 implementation. Index individual fields/claims, not only whole observations. Weight exact file paths and identifiers. Combine text relevance with active/superseded status, confidence, source type, and recency. Make ranking explainable.

Embeddings should be optional and measured. Add them only after an evaluation demonstrates that paraphrase queries still miss important records. Keep lexical anchors and an offline fallback; never send private ledger text to an external embedding provider by default. The JSONL remains authoritative, and any index is disposable.

Acceptance: representative queries recover known Eagle constraints without prior scope knowledge. Zero matches have a useful bounded response. Exact error messages and code identifiers work. Search never automatically presents a superseded claim as current truth.

## P1: Make schema usage discoverable and validation repairable

Source: scripts/ctx.py:379 validate_semantic; assets/PROJECT_CONTEXT.schema.json; references/protocol.md; SKILL.md.

Correction to the earlier conversational review: verification.details already exists in the schema and renderer. The problem is discoverability. The main skill example does not demonstrate verification, and the protocol reference explains attempt outcomes but not verification outcomes. Repeated invalid verification outcomes produce identical messages without array indexes. Runtime validation also accepts current_state.blockers as a string, while the published schema requires an array.

Implement ctx schema --section verification and ctx template observation|handoff|reflection --minimal. Give structured errors with JSON Pointer, error code, expected value, and a safe correction hint. Derive validation and documentation from one field specification, or enforce parity with tests. Distinguish agent-authored semantic input from the metadata-rich stored-entry schema.

Keep --check, which already exists. Show a file-based draft/check/append workflow so a correction does not require regenerating a large heredoc. Do not silently convert arbitrary result text into passed. Warn on likely field-name typos without making forward-compatible extension fields impossible.

Acceptance: /verification/2/outcome identifies the actual bad element; details is shown in the minimal verification example; the same malformed state is rejected by runtime and schema; examples round-trip through the validator in CI.

## P1: Fold resolved and superseded state into a current view

Source: scripts/ctx.py:966 related-entry rendering; :1716 cmd_open; :1740 cmd_blockers.

The CLI renders supersedes/resolves links in full output, but open/blockers iterate historical state directly. Those links do not currently make the queries current. Completed work can keep appearing as an old next step. Improve the deterministic projection before adding stronger natural-language summarization.

Implement an active view that follows explicit relationships, annotates superseded sources, and keeps unresolved conflicts visible. Preserve a history mode. Since an entry can contain several independent issues, support field/item-level resolution or use conservative entry-level semantics until that structure exists. Never infer that all issues are resolved just because a later entry shares a scope.

Acceptance: an explicitly resolved blocker disappears from the current blocker view but remains accessible in history; resolving one issue leaves its unrelated siblings intact; cycles and unknown references produce actionable diagnostics.

## P1: Remove sandbox and retry friction from persistence

Source: scripts/ctx.py:186 cache_root; :552 lock_path_for; :609 active_session; :1753 cmd_append.

The ledger can be writable while locks/runtime state live in a forbidden home cache. Append writes the durable entry before updating runtime state. If that later update fails, the caller can see failure after the ledger already changed, creating duplicate-retry risk. Implicit active-<host> pointers also deserve concurrent-session tests: two same-harness sessions should not attribute a manual append to each other.

Implement one configured writable runtime location resolved consistently across cooperating processes. Preserve a single canonical lock identity for a shared ledger, including git-common mode; do not silently fall back to different locks per process. Make successful ledger persistence authoritative and report ancillary runtime failures as warnings. Add an explicit idempotency key for retries. Prefer explicit/environment session identity over shared host pointers and report ambiguous fallback clearly.

Acceptance: read-only home plus writable configured runtime can append; injected runtime failure after append does not cause ambiguous success; retrying the same key creates one entry; two sessions of the same harness retain correct attribution.

## P1: Make reflection a guided, bounded task

Source: scripts/ctx.py:1871 cmd_stats; SKILL.md reflection section; references/logging-policy.md.

The Eagle ledger contains 203 observations, zero reflections. Only 12 observations have structured decisions and eight have structured attempts. These are aggregate statistics, not proof that every record needs restructuring. They show that reminding agents to reflect and providing extractors is insufficient if most usable information remains narrative-only.

Implement ctx reflect --prepare --scope <scope> --budget <n>: return the previous relevant durable state, the uncovered source IDs, changed decisions, explicit resolutions, conflicts, and a minimal output template. Let the agent write the semantic reflection. Detect eligible scopes using uncovered volume, estimated retrieval cost, and repeated content, not just total observation count. Add a non-blocking, deduplicated suggestion at a useful boundary. Require structured fields when those facts matter, but do not duplicate identical narrative in several fields.

Acceptance: a large scope can be reflected with one bounded preparation command and one append; coverage is inspectable; the resulting packet measurably shrinks while preserving constraints and open work. Automatic preparation is not permission to invent a summary or claim an unsupported resolution.

## P2: Cheaper, observable host integration

Source: scripts/install.py:719 status; scripts/ctx.py:1294 startup output; adapters/templates/*.

The capability-based architecture is sound. Current status largely checks file presence/profile. Generated subprocess adapters can discard failures and lack explicit subprocess timeouts. This limits diagnosis when an installed integration does not actually deliver memory. Source tests validate several contracts but do not establish live compatibility across all host versions.

Implement ctx doctor --host <host> --json --self-test with installed/runtime version, schema compatibility, writable paths, hook profile, last successful injection, packet hash, estimated size, and bounded error diagnostics. Expose why an integration is inactive. Enforce bounded subprocess timeouts and neutral hook responses on ancillary failures, with diagnostics outside model context. Track successfully delivered packets per session to avoid redundant injection; reset on compaction or new sessions so deduplication does not suppress needed recovery.

Split the skill into a short everyday contract and on-demand schema/install/recovery references. Keep startup-only the recommended low-overhead profile; make fuller hooks an explicit choice in new-install UX, with migration compatibility documented. Do not add a daemon or mandatory MCP service before this CLI workflow is reliable.

Acceptance: installed-but-broken hooks are distinguishable from absent ones; synthetic lifecycle replay covers each adapter's native envelope, timeout, and failure path; same-session repeats are cheap while compaction reloads the required baseline.

## Evaluation and rollout

Build a privacy-safe synthetic evaluation corpus before claiming token savings. Include scope drift, paraphrases, exact error strings, mixed reflections, long handoffs, supersession, unresolved conflicts, multiple worktrees, and sandboxed caches. Measure known-fact recall at a fixed output budget, preservation of next actions, stale-claim rate, repair attempts per append, repeated bytes delivered, startup latency, and reflection compression. Character-based budgets are estimates, not hard tokenizer guarantees across harnesses.

Suggested order:

1. Fix coverage and field-aware packing, with regression reproductions.
2. Ship semantic templates, indexed errors, validator parity, and unambiguous append results.
3. Add lexical search, scope discovery, show-by-ID, and multi-path retrieval.
4. Add active-state folding and reflection preparation.
5. Improve host health and delivery deduplication; evaluate optional embeddings against the lexical baseline.

Proposed everyday interaction, not commands that all exist today:

    ctx context --query "mobile Safari hero" --path src/components/hero --budget 1200
    ctx show <entry-id> --section current_state
    ctx template observation --minimal
    ctx append --input /tmp/checkpoint.json --check
    ctx append --input /tmp/checkpoint.json --idempotency-key <session-task>

The goal is one useful recall, one cheap expansion if necessary, and one accurate checkpoint at a meaningful boundary. Keep the rich ledger; reduce the agent's effort to select, write, repair, and trust it.

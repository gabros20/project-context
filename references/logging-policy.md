# Logging policy

Read this when deciding whether to append an observation or how much context to preserve.

## Record durable project knowledge

Good candidates:

- implemented or changed behavior;
- architectural or API decisions and rationale;
- non-obvious constraints/invariants;
- important debugging discoveries;
- failed approaches another agent could repeat;
- successful approaches whose preconditions matter;
- verification results and known gaps;
- created artifacts/docs and why they matter;
- blockers and unresolved questions;
- a meaningful handoff frontier;
- changed facts that supersede prior context.

## Do not record routine narration

Do not create memory merely because the agent:

- read files;
- ran grep/search;
- ran a formatter;
- executed a normal tool call;
- thought about options without producing durable insight;
- generated large logs/build output;
- observed something obvious and cheaply recoverable from Git.

## Context quality

`context` should be rich enough that a fresh agent can reconstruct the relevant mental model without the original chat.

Useful content includes:

- initial problem/state;
- why the change was needed;
- important constraints;
- what changed and how;
- why this approach was chosen;
- important alternatives and failure modes;
- meaningful evidence;
- current caveats and frontier.

Avoid a long chronological transcript of actions. Prefer a coherent engineering narrative.

## Soft length guidance

- routine durable observation: about 100–300 words;
- significant observation: about 300–700 words;
- critical observation / handoff: 500–1,200+ words when required;
- reflection: enough to replace most covered observations for normal startup retrieval.

These are not hard caps.

## Failed work

If an approach failed, preserve enough detail to prevent another agent from repeating it blindly:

```json
{
  "approach": "...",
  "outcome": "failed",
  "reason": "...",
  "evidence": "...",
  "learning": "..."
}
```

## Reasoning

Preserve decision-relevant engineering rationale in structured fields such as `rationale`, `reason`, `evidence`, and `learning`. Do not dump private scratchpad-style chain-of-thought or a verbatim conversation trace.

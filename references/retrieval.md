# Retrieval strategy

Read this when startup context is insufficient or when deciding which historical slice to retrieve.

## Default rule

Never read the full JSONL solely because it exists.

Use one targeted `ctx` query and let the CLI project structured records into plain text.

## Typical queries

```bash
ctx context --scope auth
ctx context --path src/auth/session.ts
ctx context --scope auth --path src/auth/session.ts --budget 4000
ctx latest 12
ctx since 2026-08-17T09:30:00Z
ctx decisions --scope auth
ctx attempts --scope auth --outcome failed
ctx open --scope auth
ctx blockers
```

## Reflection + tail

`ctx startup` and `ctx context` prefer:

1. latest relevant reflection;
2. latest relevant handoff;
3. high/critical records after reflection coverage;
4. newest medium records after coverage until the budget is filled.

This gives the agent durable state plus the unreflected frontier.

## Budgets

Repository config controls approximate token budgets. The implementation estimates tokens conservatively from characters; it does not require a tokenizer dependency.

Recommended defaults:

- session-start: 2200 tokens
- compact/resume refresh: 1200 tokens
- explicit retrieval: 3000 tokens

Increase explicit retrieval before increasing global startup context.

## Raw modes

Use `--format jsonl` only when machine processing or exact field inspection is required. Use `--full` when more structured detail is needed in plain output.

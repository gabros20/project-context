# Host compatibility sources

Compatibility was re-verified against first-party documentation on 2026-08-17. This file records the design inputs; `adapters/HOSTS.json` is the machine-readable capability manifest.

## Claude Code

- Hooks: https://docs.anthropic.com/en/docs/claude-code/hooks
- Skills: https://docs.anthropic.com/en/docs/claude-code/skills

Adapter: command hooks in user/project Claude settings; `CLAUDE.md` imports the canonical repo `AGENTS.md` block.

## Codex

- Hooks: https://developers.openai.com/codex/hooks
- Skills: https://developers.openai.com/codex/build-skills
- AGENTS.md: https://developers.openai.com/codex/agent-configuration/agents-md

Adapter: command hooks in `~/.codex/hooks.json` or `.codex/hooks.json`; skills through `.agents/skills` / `~/.agents/skills`; project hooks may require trust/review.

## Grok Build

- Skills/plugins/hooks overview: https://docs.x.ai/build/features/skills-plugins-marketplaces
- Hooks: https://docs.x.ai/build/features/hooks
- AGENTS.md: https://docs.x.ai/build/features/project-rules

Adapter: native command hooks under `.grok/hooks/` or `~/.grok/hooks/`; Grok also supports Agent Skills and Claude-compatible configuration. Project hooks require trust.

## OpenCode

- Agent Skills: https://opencode.ai/docs/skills/
- Rules / AGENTS.md: https://opencode.ai/docs/rules/
- Plugins: https://opencode.ai/docs/plugins/

Adapter: generated local JS plugin; session events are used for lifecycle auditing and `experimental.session.compacting` injects project memory into compaction. `AGENTS.md` remains the reliable bootstrap path for initial task context.

## Cursor CLI

- Agent Skills: https://cursor.com/docs/skills
- CLI rules/instructions: https://cursor.com/docs/cli/using
- Hooks: https://cursor.com/docs/hooks

Adapter: native `.cursor/hooks.json`; Cursor documents `sessionStart` context injection, prompt hooks, stop follow-up, compaction, and session end. Cursor loads `.agents/skills` and `.cursor/skills` at project/user scope.

## Factory Droid CLI

- Skills: https://docs.factory.ai/harness/skills
- AGENTS.md: https://docs.factory.ai/harness/agents-md
- Hooks: https://docs.factory.ai/harness/hooks

Adapter: native `.factory/hooks.json`; project/personal skills use `.factory/skills`; use absolute command paths because hook cwd is not guaranteed to be the repo root.

## Pi / pi-mono

- Skills: https://pi.dev/docs/latest/skills
- Usage / context files: https://pi.dev/docs/latest/usage
- Extensions: https://pi.dev/docs/latest/extensions

Adapter: generated TypeScript extension in `.pi/extensions/` or `~/.pi/agent/extensions/`. `before_agent_start` can inject a persistent message; compaction/session events provide lifecycle boundaries.

## Google Antigravity CLI

- Skills: https://antigravity.google/docs/skills
- Hooks: https://antigravity.google/docs/hooks
- Best practices/instructions: https://antigravity.google/docs/cli/best-practices

Adapter: Agent Skills in `.agents/skills` or `~/.gemini/config/skills`; project hooks in `.agents/hooks.json`, user hooks in `~/.gemini/config/hooks.json`; `PreInvocation` injects ephemeral project context and Stop can continue the loop.

## Hermes Agent

- Skills: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- Event hooks: https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks
- Plugins: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins

Adapter: agentskills.io-compatible user skill under `~/.hermes/skills`; generated Hermes plugin uses session lifecycle, `pre_llm_call` context injection, and `pre_verify` continuation when coding work needs another pass.

## OpenClaw

- Skills: https://docs.openclaw.ai/tools/skills
- Workspace: https://docs.openclaw.ai/concepts/agent-workspace
- Hooks: https://docs.openclaw.ai/automation/hooks

Adapter: skill via workspace/`.agents/skills`/personal/global discovery; internal hook pack uses `agent:bootstrap` to add a generated project-context bootstrap file and tracks compaction/reset boundaries. OpenClaw internal hooks are not treated as an equivalent coding-CLI Stop gate.

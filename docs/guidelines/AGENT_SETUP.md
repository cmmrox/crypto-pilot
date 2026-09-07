# Shared repository agent setup

Both tools use the same checked-in guidance and project references:

```text
AGENTS.md                              shared bootstrap
CLAUDE.md -> AGENTS.md                  Claude bootstrap adapter
.agents/skills/cryptopilot-dev/
  SKILL.md                             shared workflow and documentation router
  agents/openai.yaml                   Codex discovery metadata only
  scripts/validate-agent-setup.sh       repository containment and reference checks
.claude/skills/cryptopilot-dev
  -> ../../.agents/skills/cryptopilot-dev
                                       Claude skill discovery adapter
docs/                                  authoritative shared project references
  strategies/NAMING.md                  single strategy naming policy
  strategies/CREATING_A_STRATEGY.md      implementation and validation procedure
```

Edit the canonical skill once; do not copy separate Codex/Claude instructions.
Project code, skill bodies, scripts, templates and maintained guidance belong inside
this repository. Use relative internal links; do not require a personal skills
folder, memory entry or another checkout for project behavior. Optional installed
tools may assist a task, but project policy must remain available from this checkout.
Keep credentials and machine-specific permissions outside tracked instruction files.
`.claude/settings.local.json` stays ignored; no credential migration is required.

Keep symlinks when cloning/checking out. Run the validator from any repository
subdirectory after changing guidance. CI runs the same validator. It rejects
missing references and agent files/symlinks resolving outside this repository.
Put durable rules in `docs/` and link them from the skill's task routing table.

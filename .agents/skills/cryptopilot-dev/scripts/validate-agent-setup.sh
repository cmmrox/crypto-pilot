#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

fail() {
  printf 'agent setup invalid: %s\n' "$1" >&2
  exit 1
}

[[ -f .agents/skills/cryptopilot-dev/SKILL.md ]] ||
  fail "canonical SKILL.md is missing"
[[ -f .agents/skills/cryptopilot-dev/agents/openai.yaml ]] ||
  fail "Codex agents/openai.yaml is missing"

[[ -L .claude/skills/cryptopilot-dev ]] ||
  fail ".claude skill must be a symlink"
[[ "$(readlink .claude/skills/cryptopilot-dev)" == "../../.agents/skills/cryptopilot-dev" ]] ||
  fail ".claude skill points somewhere unexpected"
[[ "$(realpath .claude/skills/cryptopilot-dev)" == \
   "$(realpath .agents/skills/cryptopilot-dev)" ]] ||
  fail "Claude and Codex do not resolve to the same skill directory"

[[ -L CLAUDE.md ]] || fail "CLAUDE.md must be a symlink"
[[ "$(readlink CLAUDE.md)" == "AGENTS.md" ]] ||
  fail "CLAUDE.md must point to AGENTS.md"
[[ "$(realpath CLAUDE.md)" == "$(realpath AGENTS.md)" ]] ||
  fail "Claude and Codex do not resolve to the same bootstrap file"

required_paths=(
  docs/BUSINESS_SOLUTION_v2.pdf
  docs/strategies/NAMING.md
  docs/strategies/CREATING_A_STRATEGY.md
  docs/guidelines/AGENT_SETUP.md
  docs/plan/IMPLEMENTATION_PLAN.md
  docs/architecture/ARCHITECTURE.md
  docs/architecture/DATABASE_ARCHITECTURE.md
  docs/architecture/INTEGRATIONS.md
  docs/qa/QA_STRATEGY.md
  docs/guidelines/BACKEND_GUIDELINES.md
  docs/guidelines/FRONTEND_GUIDELINES.md
  docs/guidelines/UIUX_GUIDELINES.md
  docs/guidelines/TESTING_GUIDELINES.md
  docs/guidelines/CODE_REVIEW.md
  research/backtests/final_composite.py
  prototype/final-cryptopilot
)

for path in "${required_paths[@]}"; do
  [[ -e "$path" ]] || fail "referenced path is missing: $path"
  [[ "$(realpath "$path")" == "$repo_root/"* ]] || fail "reference escapes repository: $path"
done

while IFS= read -r -d '' path; do
  [[ "$(realpath "$path")" == "$repo_root/"* ]] ||
    fail "agent file escapes repository: $path"
done < <(find .agents .claude/skills -print0)

printf 'agent setup valid: Claude Code and Codex share one bootstrap and one skill\n'

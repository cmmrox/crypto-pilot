# CryptoPilot agent bootstrap

For every task in this repository, load and follow the `cryptopilot-dev` project skill
before taking action. Its canonical file is:

`./.agents/skills/cryptopilot-dev/SKILL.md`

The skill routes work to the authoritative documents in `docs/` and defines the safety,
workflow, testing, and review gates for this real-money trading system. Do not duplicate
those rules here. If the skill and a project document differ, treat
`docs/BUSINESS_SOLUTION_v2.pdf` plus the approved deviations in
`docs/architecture/ARCHITECTURE.md §8` as authoritative.

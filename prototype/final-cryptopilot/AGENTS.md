# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

## Approved CryptoPilot direction

- Use `https://business-solution-prototype.cmmrox.chatgpt.site` as the visual reference: restrained black control-room shell, amber section labels, mint operational states, compact bordered cards, Geist typography, and straightforward data tables.
- `BUSINESS_SOLUTION_v2.pdf` is the feature authority and Trend Rider v6 long/short is the deployed strategy.
- The active strategy must be prominent globally and on the Overview.
- Strategy parameters are deployed, validated, and read-only in the operator UI. A strategy release can be selected only while the bot is stopped.
- Login requires username, password, and mandatory TOTP with no bypass.
- Preserve strong dark-mode contrast and responsive behavior.
- The final prototype must expose the complete owner workflow, not only the Overview screen.

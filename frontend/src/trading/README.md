# Trading status display

`TradingStatusProvider` is mounted only within an authenticated session. It owns
one server-confirmed `/api/bot/status` snapshot shared by Shell and Settings.
Consumers call `refresh` after an accepted mutation. Polling and focus refresh
capture changes from another tab; request generations fence stale responses.
Unknown or failed account status never falls back to DEMO. This module displays
state and does not place orders or decide which exchange account to use.

# Stage 5 — Deploy & monitoring

Artifact: `05-release.md`. Gate: Деплой / Откат / Мониторинг ошибок filled, or `N/A — <reason>` per section.

Why: safe automated delivery, and errors must not get lost — the deploy should let the agent see an error, understand the cause and prepare a fix for a new check (slide "Этап 5").

| Section | Answer |
|---|---|
| Деплой | how it ships (CI job, feature flag, canary); who presses the button. The agent never deploys or pushes without explicit consent |
| Откат | exact rollback in minutes (revert commit, flag off, previous image) |
| Мониторинг ошибок | where errors land (logs, Sentry, alerts) and how an agent can read them for the next fix |

`N/A` is legitimate for a local-only project but needs the reason — and if monitoring is N/A while production exists, that is a finding to raise with the human, not to hide.

Exit: `rails.py check release` → OK → `rails.py advance`.

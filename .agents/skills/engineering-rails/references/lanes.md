# Lanes — same stages, different depth

Stages are never skipped. Lanes only change how much each artifact must contain.

| Lane | Use when | Design | Plan | Release |
|---|---|---|---|---|
| hotfix | a defect in existing behaviour, fix touches ≤ ~2 files, no new concept | Симптом+ожидаемое, Причина, AC with regression test | 1–3 steps | usually `N/A — reason` or one line |
| small | additive change, ≤ ~3 files, no new domain entity, no schema/API contract change | Задача, Решение, AC | steps | short |
| feature | new domain concept, API/schema/contract change, money/security/data, multiple modules, or any LLM/agent feature | full (alternatives, risks…) | full (boundaries, parallel, review) | full |

Rules:
- Pick the lane with a one-line reason in `--why`. When unsure, pick the larger lane.
- Lane = size and risk of the change, never urgency. A deadline makes artifacts shorter inside the right lane; it does not turn a new endpoint into a hotfix. hotfix is only for restoring existing, specified behaviour.
- hotfix/small: design and plan are drafted together and approved with one answer (`approve design+plan`).
- Upgrade any time (`rails.py lane feature --why ...`) — e.g. a "typo fix" that touches money logic.
- Downgrade only with the human's explicit words (`--quote`).
- Money, auth, personal data, irreversible operations → never hotfix-shortcut the design: the expected behaviour must come from a confirmed business rule.
- `--ai` is orthogonal to the lane: any task that adds or changes LLM/agent behaviour gets an EVALs section in verify.

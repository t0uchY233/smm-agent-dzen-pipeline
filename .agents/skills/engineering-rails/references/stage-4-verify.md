# Stage 4 — Verification & Review (quality gates)

Artifact: `04-verify.md`. Gate: Автоматические проверки with real commands + results, every AC from the design as `- AC-n: PASS — <evidence>`, Human review section, `## EVALs` when the task is `--ai`; **human approval**.

Why: blind faith is dangerous — multi-level checking (tests → EVALs → human) is the foundation of production (slide "Этап 4" funnel).

| Layer | What | Rule |
|---|---|---|
| Auto gates | tests, linters, type checks, build | Paste the actual command and its actual result. If it could not run (blocked, missing env), write that — then the AC is not PASS and the human decides |
| EVALs (AI features) | scenario set, metric, threshold, result | See `ai-features.md` |
| Human | zones where the machine is not trusted: money, security, personal data, irreversible actions, UX copy | Name the zones, show the human the specific diff/output to check |

A test that never ran is not evidence. "Should work" is not evidence. Never mark PASS on reasoning alone.

Blocked check (the environment refuses to run tests, no API key, no staging): don't stall in implement and don't repeat "still blocked" every turn. Do this once:
1. Finish implement (tick the steps whose code is done), `RAILS advance` to verify.
2. Record the real refusal output under Автоматические проверки.
3. Ask the human, in one message, to choose: fix the environment (say exactly what is needed) OR accept the risk for named ACs.
4. Only if they accept: `- AC-n: RISK-ACCEPTED — <what is unverified, why> — человек: «<their words>»`. Their verify approval is still required; the retro lists the accepted risks.

Exit checklist:
- [ ] `rails.py check verify` → OK
- [ ] Human looked at the review zones → `rails.py approve verify --quote "..."`

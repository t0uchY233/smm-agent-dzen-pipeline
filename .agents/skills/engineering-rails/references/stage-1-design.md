# Stage 1 — Research & Design

Artifact: `.rails/tasks/<id>/01-design.md`. Gate: lane sections filled, acceptance criteria as `- AC-n: <fact> — проверка: <how>`, feature lane ≥ 2 alternatives, **human approval**.

Why: the engineer validates assumptions and makes decisions BEFORE implementation; the agent only helps work out options (slide "Этап 1"). Code written before decisions is the code "rewritten 100 times".

| Step | Key point | Why |
|---|---|---|
| 1. Restate the business goal | who suffers, what changes for them | "Add promo codes" hides 10 decisions: stacking, expiry, limits, who creates codes |
| 2. Read the affected code + `.rails/context.md` | name the exact modules you will touch | Design must fit the existing system, not a blank page |
| 3. List open business questions | each with your recommended default | The human answers in seconds when you propose; they stall when you ask open-ended |
| 4. Alternatives (feature lane: ≥ 2) | pros/cons in one line each | Comparing options is what turns a guess into a decision |
| 5. Write acceptance criteria | observable facts + how each will be checked (test name, manual check by whom) | Stage 4 verifies exactly these; vague AC = unverifiable work |
| 6. Show the design, ask for approval | short summary + the open questions in chat, not just "ok?" | Approval of something the human hasn't seen is not approval |

Investigation is allowed and encouraged here: reading code, running the app, reproducing a bug, quick throwaway experiments in a scratch dir. Changing project source files is not — that is stage 3.

Hotfix lane: "Симптом и ожидаемое поведение" must state the expected behaviour by a business rule the human confirms (e.g. "discount rounded before tax?") — the bug report says what is wrong, not what is right. Reproduce first; the regression test AC is mandatory.

Exit checklist:
- [ ] `rails.py check design` → OK
- [ ] Every assumption about business rules is either confirmed by the human or listed under risks
- [ ] Human approved in their own words → `rails.py approve design --quote "..."`

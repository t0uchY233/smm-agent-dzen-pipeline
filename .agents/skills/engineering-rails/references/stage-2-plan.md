# Stage 2 — Plan & orchestration

Artifact: `02-plan.md`. Gate: steps as `- [ ] S<n>: <what> — файлы: a.py, b.py`; feature lane also Границы / Параллелизация / Ревью; **human approval**.

Why: the plan is the fence for implementation. `rails.py can-edit` and the implement gate only allow files listed here, so scope creep becomes visible instead of silent.

| Step | Key point | Why |
|---|---|---|
| 1. Slice into small steps | each step ends in a runnable, testable state; writing tests is a step too | Small steps keep review cheap — slide "узкое место": review is where speed is lost |
| 1a. Steps are changes, not checks | "add regression test", "switch to Decimal" — never "run unittest" or "reproduce" as a step | Running checks is stage 4 (verify). A run-step can't be ticked when the environment blocks tests, so implement never closes and the human never gets the RISK-ACCEPTED choice |
| 2. List files per step | globs allowed (`tests/test_promo*.py`) | Explicit scope = predictable diff |
| 3. Mark boundaries (feature) | what we deliberately do NOT touch | Stops "while I'm here" refactors |
| 4. Parallelization (feature) | which steps are independent, who/what agent takes them, how results merge; or "sequential because …" | Parallel agents only help inside a strict process |
| 5. Review plan (feature) | who reviews what after implementation | Decide the human-review zones now, not after the fact |
| 6. Show plan, ask for approval | | Same rule as design |

Exit checklist:
- [ ] `rails.py check plan` → OK
- [ ] Tests appear as explicit steps (or inside a step's files)
- [ ] Human approved → `rails.py approve plan --quote "..."`

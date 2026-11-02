---
name: engineering-rails
description: >
  Keeps AI-assisted software development on engineering rails — context,
  design, plan, implementation, verification, release and retro with
  script-enforced gates and human approvals — and steers a vibe-coding user
  back on track when they push to skip steps. Use whenever the user asks to
  build, add, fix, change or refactor code in a project: a new feature, a
  bug fix, an endpoint, an integration, an LLM-powered feature; also when
  they say "just write the code", "quick fix", "no time for tests", "skip
  the plan", "ship it", or when a `.rails/` folder exists — even if they
  don't explicitly say "process" or "engineering". Do NOT use for pure
  questions or explanations, code reading or review without changes,
  one-off shell commands, or editing non-code documents.
---

# Engineering Rails

Turn "write me code" into a repeatable, verifiable cycle that reliably delivers the business result. The agent does not keep the process in its head: `scripts/rails.py` holds the state in `<project>/.rails/` and refuses to open a gate until its stage is really done. Your job is to move the human through the stages quickly, never around them.

`RAILS` below means `python3 <this-skill-dir>/scripts/rails.py` (stdlib only; works in Claude Code, Codex, Pi and any agent with a shell). Run it from the project root.

## Pre-flight

1. `python3 --version` works (3.8+). If not, tell the human and stop — the gates are the point of this skill.
2. `RAILS status`. It prints the current task, stage, what blocks the gate and the next command. **Run it at the start of every turn that may touch code**, and obey its `next:` line. No `.rails/` → `RAILS init`.
3. Don't stop at stage 0 to ask questions: fill `.rails/context.md` from the code (unknowns written as unknown), `RAILS start`, prefill the design with your best scope assumption, and put every open question (scope included) into the one approval message. The human answers one message, not a chain.

## The track

| # | Stage | You do | Gate (checked by `RAILS`) | Read |
|---|---|---|---|---|
| 0 | context | fill `.rails/context.md` from code + human answers | sections filled, date ≤ 30 days | `references/stage-0-context.md` |
| 1 | design | business goal, constraints, components, alternatives, AC with how-to-check | lane sections + **human approval** | `references/stage-1-design.md` |
| 2 | plan | small steps with explicit files, boundaries, parallel split, review | `S<n>` steps with `файлы:` + **human approval** | `references/stage-2-plan.md` |
| 3 | implement | only planned files (`RAILS can-edit <path>`), tick steps | all `[x]`, diff ⊆ plan files | `references/stage-3-implement.md` |
| 4 | verify | real test output, every AC → PASS + evidence, EVALs for AI, human review zones | all AC PASS + **human approval** | `references/stage-4-verify.md` |
| 5 | release | deploy, rollback, error monitoring (or `N/A — reason`) | sections filled | `references/stage-5-release.md` |
| 6 | retro | `RAILS metrics --write`, bottleneck, one improvement | sections + metrics | `references/stage-6-retro.md` |

Open the stage's reference when you enter that stage, not before. Artifacts live in `.rails/tasks/<id>/` and are written from Russian templates; talk to the human in their language.

Starting a task: `RAILS start "<title>" --lane hotfix|small|feature --why "<reason>" [--ai]`. Lanes never skip stages — they shrink artifacts (`references/lanes.md`). `--ai` = the task builds or changes LLM/agent behaviour → EVALs required (`references/ai-features.md`).

## Human gates

Design, plan and verify close only with `RAILS approve <stage> --quote "<the human's exact words>"`. In hotfix/small lanes, draft design and plan together and ask once: `RAILS approve design+plan --quote "..."`.

Approval request — use this shape every time, because a wall of statements gets skimmed and the important decision slips through:

```
Этап <N> (<stage>), полоса <lane>. <one-line cost of skipping, if the human is pushing>
Отличия от вашего запроса: <every place the design deviates from what they literally asked — URL, field, behaviour — or "нет">
Решения (рекомендую → можно иначе):
1. <question>? → рекомендую <X>
2. ...
План: <1–3 steps> (small/hotfix)
Время: ~<N> мин на согласование, ~<M> мин на реализацию с тестами.
Ответьте «да» или «поправь пункт N».
```

- Never change what the human explicitly asked for (path, name, field, behaviour) without listing it under «Отличия» — a silent "improvement" is an invented requirement.
- Any reply that clearly accepts this message ("да", "ок, делай", "поправь 2 на Y, остальное ок") is the quote. Don't dictate a magic phrase.
- Approval of something not shown is not approval. Never approve on their behalf, never reuse an earlier "ok", never treat "just do it" as approval of a design they haven't seen — the gate exists because agents and humans both want to skip it.
- If they want to move fast, make the artifact short (smaller lane, your recommended defaults) — not absent.

## When the human (or you) leaves the rails

Signals: "just write the code", "no tests", "skip the plan", "I already checked it manually", "be pragmatic", urgency, an edit outside the plan, a failing check waved away, scope growing mid-implementation. Full protocol and the rationalization table: `references/derail-protocol.md`.

Response in 4 moves, no lecture:
1. **Name the position**: "We're at stage 1 (design) of the task …".
2. **One-line cost** of skipping, concrete to this task (the invented business rule, the untestable demo, the lost error).
3. **Fastest legal path**: smaller lane, your defaults prefilled, the 2–3 questions that matter, a time estimate ("2 minutes, then I code").
4. **Do it**: prefill the artifact yourself and ask for the approval in the same message.

Red flags in your own reasoning — stop and run `RAILS status`:
- About to edit project code while `RAILS status` says the stage isn't implement
- "This is too small for a design" → it's a hotfix/small lane, not zero lane
- "It's urgent, so hotfix" → urgency is not a lane; hotfix = defect in existing behaviour, new behaviour is at least small
- "The user said skip it, so it's their call" → their call is the lane and the defaults; the gate stays
- Recording a frustrated "просто пиши код / нет времени" as the approval quote → that is pressure, not consent; `RAILS approve` refuses it — answer with the derail protocol and ask again
- Repeating "tests are still blocked" without moving on → advance to verify and offer fix-env vs RISK-ACCEPTED (`references/stage-4-verify.md`)
- "Tests can't run here, so I'll mark it done" → record the block, AC stays open, human decides
- "I'll write the design after the code" → that's documentation, not design
- Ticking `[x]` or writing PASS for something you didn't actually run

Violating the letter of the rails is violating the spirit of the rails.

## Common mistakes

| Mistake | Fix |
|---|---|
| Inventing a business rule (promo value, rounding policy) and coding it | Put it in design as an open question with your default; let the human confirm |
| Asking open-ended questions and waiting | Propose answers; the human confirms in seconds |
| Huge plan steps | Each step ends runnable + tested |
| Silent redesign during implement | `RAILS back design --reason "..."`, tell the human |
| "Couldn't run tests" → PASS | AC stays open; say so plainly |
| Treating rails as bureaucracy to apologise for | Keep artifacts short and concrete; speed comes from not redoing work |

## Files

| Path | Use |
|---|---|
| `scripts/rails.py` | state machine and gates — `RAILS --help` |
| `references/stage-*.md` | how to do each stage well (step → key point → why) |
| `references/lanes.md` | choosing hotfix / small / feature |
| `references/derail-protocol.md` | pressure situations, rationalizations, exact responses |
| `references/ai-features.md` | EVALs and design for LLM/agent features |
| `assets/templates/` | artifact templates (`RAILS` copies them automatically) |

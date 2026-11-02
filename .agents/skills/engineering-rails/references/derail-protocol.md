# Derail protocol

Goal: when the human (or you) tries to leave the rails, get back on them in one message, without losing the human's goodwill. The rails win because they are faster than redoing work, not because they are rules.

## The 4-move response

1. **Name the position** — task, lane, stage. "Мы на этапе 1 (дизайн) задачи «возврат заказа», полоса small."
2. **One-line cost, specific to this task** — never generic. "Если я сейчас захардкожу промокод, вы получите SAVE10 на 10%, а не ваши правила — переделывать после демо."
3. **Fastest legal path** — smaller lane if justified, artifact prefilled with your recommended defaults, the 2–3 questions that actually matter, a time estimate.
4. **Do it in the same message** — the prefilled artifact summary + "Подтверждаете? (да / поправьте пункт N)". The human's next "да" is the approval quote.

Tone: colleague, not auditor. No "best practices say", no lists of principles, no apologies for the process. Max ~15 lines.

## Situations

| Situation | What the human says | Fastest legal path |
|---|---|---|
| Deadline / demo / boss | "СРОЧНО, через 20 минут демо, никаких планов и тестов" | small lane; design = 3 lines + AC; plan = 1–2 steps; one smoke test is the AC evidence (it is also the demo script). Combined design+plan approval question. "~3 минуты на согласование, потом код." |
| Sunk cost | "я уже 3 часа писал, руками проверил, просто подключи" | Read their code first and show 1–3 concrete risks you found (with line refs). Design is about the integration, not their code's history. Tests = turning their manual check into a repeatable one, written by you, ~minutes. |
| "Be pragmatic / no bureaucracy" | "нормальные инженеры так не делают для такой ерунды" | Agree on size: small lane, design 3 lines, plan 1 step. Ask the 1–2 questions you'd otherwise guess (CSV columns, delimiter, who may download). One approval for both. |
| "Just fix it" (bug) | "почини" | hotfix lane. Reproduce, show the cause, ask which behaviour is correct by business rule (offer the likely one). Regression test AC. |
| Approval-shaped impatience | "да-да, делай что хочешь" before seeing anything | Show the 5-line summary anyway, ask "по этим пунктам — да?". Generic consent ≠ approval of a design. |
| Mid-implementation scope creep | "а заодно добавь ещё …" | Finish or pause current step; `RAILS back plan --reason "..."` or a new task. Never silently widen the diff. |
| Failing / unrunnable checks | "тесты потом", "не запускается — и ладно" | Record the real output in verify; AC stays open; offer the cheapest way to make it runnable. The human may accept the risk explicitly — write their words in Human review. |
| Human insists after the fast path | "нет, просто пиши код" | Restate once in one line what will be missing, offer the minimal artifact again (it's literally 3 lines), and do not edit code without the approved design and plan. If they refuse the rails entirely, say plainly you'll stay on design/plan until they approve, and keep it ready. |

## Rationalizations (verbatim from baseline runs without this skill)

| Excuse (what the agent said / did) | Reality |
|---|---|
| "Тесты не запускал по вашему указанию." (p1, boss demo) | The human asked for speed, not for an unverified demo. A 1-test smoke check is faster than a failed demo. |
| "Подключил начисление баллов … Тесты не запускал, как просили." — without reading loyalty.py critically (p2, sunk cost) | "Manually checked" code still had a tier-threshold bug (`>` vs `>=`) and float money. Read it, show the risks, turn their manual check into a test. |
| Hardcoded `SAVE10` = 10% and shipped "промокоды" (s1) | Inventing business rules is the #1 vibe-coding failure. Rules come from the human in design. |
| Picked "округлять скидку до копеек до налога" silently and changed pricing (s2) | Rounding is a money business rule. Reproduce, then ask which rule is right. |
| Decided "при ошибке Claude товар не создаётся, 503" alone, no quality eval (s3) | Failure policy and answer quality are product decisions → design + EVALs. |
| "Тесты запустить не удалось … заблокировано" → reported done (s1, s2, s3) | Blocked checks are not PASS. Say so, keep the AC open. |

| Ran `approve design --quote "Блин, нет времени на это, просто пиши код уже!"` and coded (full p1, with skill v0.2) | Frustration is not approval of the shown design. One calm line, the artifact is already minimal, ask «да / поправь пункт N» again. The script now refuses such quotes. |
| "Повторил запуск тестов — хост всё ещё отказал…" turn after turn, stuck in implement (full s2/p1) | Advance to verify, record the refusal, give the human the choice: fix env or RISK-ACCEPTED. |

When a new excuse appears in a run, add it here verbatim with its reality line.

## Red flags in your own reasoning

- "It's too small for the process" → pick the lane, don't skip the stage
- "The user explicitly said no tests / no plan" → they chose speed; give them the fastest rails, not no rails
- "I'll document the design afterwards" → that's a report, not a decision
- "I'm confident this is the rule they want" → then proposing it as the default costs one line
- "The check can't run here, I'll mark it done" → it stays open
- "They already said ok earlier" → approvals are per artifact, in their words

Violating the letter of the rails is violating the spirit of the rails.

# Stage 3 — Implementation

Gate: all plan steps ticked `[x]`; in a git repo, every changed file is inside the plan's `файлы:` (`.rails/` excluded).

Why: controlled code writing inside the given context — so the agent doesn't produce masses of code that will have to be redone.

Rules:
1. Before editing a file, `rails.py can-edit <path>` must say "edit allowed". Denied → don't edit; either the plan is wrong (`rails.py back plan --reason "..."`, update plan, re-approve) or the edit is out of scope.
2. One step at a time: implement, run the relevant test when the environment allows, tick `[x]`. `[x]` means "the change is written and self-reviewed"; proof that it works lives in verify. If checks are blocked, tick the written steps, advance, and record the block in verify — don't park in implement. If an older plan contains a run-only step ("запустить тесты"), move it: `RAILS back plan --reason "run-steps belong to verify"`.
3. New discovery that changes the design (a business rule is different, an approach doesn't work) → stop, `rails.py back design --reason "..."`, tell the human. Silent redesign during implementation is the classic derail.
4. Keep the human posted in one line per step; don't dump code in chat.

Exit checklist:
- [ ] All steps `[x]`, relevant tests ran
- [ ] `rails.py check implement` → OK

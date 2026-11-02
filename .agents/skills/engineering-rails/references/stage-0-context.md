# Stage 0 — Context (project knowledge base + agent access)

Artifact: `.rails/context.md` (project-level, shared by all tasks). Gate: every section filled, no placeholders, `Актуально на:` date ≤ 30 days old.

Why: an agent without architecture and business rules "generates garbage" — it invents rules (a hardcoded promo code, a rounding policy) instead of following the real ones. This stage is the cheapest place to prevent that.

| Step | Key point | Why |
|---|---|---|
| 1. Read the real project first | entry points, modules, tests, README, configs, deploy files, existing docs | Facts from code beat the human's memory; you fill most sections yourself |
| 2. Draft every section from evidence | cite files (`shop/pricing.py: money is float`) | A context doc that is not grounded in code goes stale on day one |
| 3. Ask the human only what code cannot tell | business rules, who the users are, what production looks like, what the agent must never touch | These are exactly the facts agents otherwise guess |
| 4. Write access rules explicitly | allowed dirs, forbidden: secrets, prod DB, other services, pushing/deploying without consent | Slide "Безопасность": strict control of what data the agent touches |
| 5. Set `Актуально на:` to today | refresh when `status` reports it stale or when a task changes architecture | Outdated docs mislead worse than no docs |

Questions to ask (in the human's language, max 5 at once, offer your best guess for each so they can just confirm):
- Which business rules must never break here (money, limits, permissions)?
- Is there production? Where do errors go?
- What must the agent never read or change?
- Any past decisions I should respect (and why)?

Exit checklist:
- [ ] `rails.py check context` → OK
- [ ] Nothing in the file is invented: unknowns are written as unknown ("Продакшена пока нет")

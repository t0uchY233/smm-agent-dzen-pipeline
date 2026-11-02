# AI features (LLM / agent inside the product)

Start the task with `--ai` when it adds or changes behaviour produced by a model: generation, classification, extraction, chat, agents, tool use, RAG.

Why: model output is non-deterministic; unit tests catch plumbing, not answer quality. EVALs are scenarios that score the quality of answers and the correctness of the system's actions.

What changes per stage:
- Design: add to AC at least one quality criterion with a threshold ("≥ 90% of 20 eval cases rated acceptable by rubric X") and a failure policy (what the product does when the model fails/times out). Note cost and latency budgets. Data sent to the model is an access question → check `.rails/context.md` "Доступы агента".
- Plan: an explicit step to build the eval set (cases + rubric + runner) BEFORE wiring the feature in.
- Verify: `## EVALs` — dataset path, metric, threshold, actual result, notable failures.

If the `developing-ai-agents` skill is available, load it for the design of context, tools, eval plans and trace diagnosis (its `references/playbooks/build-evals.md` and `references/templates/eval-plan.md`). If not, minimum viable eval: 10–20 realistic cases incl. edge cases, a written rubric, run it, record the pass rate.
